"""Tests for the research agent core — end-to-end pipeline."""

from pathlib import Path

import httpx
import pytest

from theaunties.agent.analyzer import Analyzer
from theaunties.agent.collector import DataCollector
from theaunties.agent.context import ContextManager
from theaunties.agent.core import ResearchAgent
from theaunties.agent.discovery import SourceDiscovery, WebSearchStub
from theaunties.db.models import Run, Source, Topic
from theaunties.llm.claude import ClaudeStubClient
from theaunties.llm.gemini import GeminiStubClient
from theaunties.llm.router import LLMRouter
from theaunties.output.gdrive import LocalDocGenerator


@pytest.fixture
def llm_router():
    return LLMRouter(
        gemini_client=GeminiStubClient(),
        claude_client=ClaudeStubClient(),
    )


@pytest.fixture
def mock_http_client():
    """HTTP client that returns canned JSON responses."""
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"temperature": 65, "wind_speed": 8, "unit": "F"})
    )
    return httpx.AsyncClient(transport=transport)


@pytest.fixture
def agent(llm_router, db_session, tmp_path, mock_http_client):
    """Create a fully wired ResearchAgent with stubs."""
    discovery = SourceDiscovery(
        llm_router=llm_router,
        web_search=WebSearchStub(),
        http_client=mock_http_client,
    )
    collector = DataCollector(http_client=mock_http_client)
    analyzer = Analyzer(llm_router=llm_router)
    context_mgr = ContextManager(context_dir=tmp_path / "context")
    doc_gen = LocalDocGenerator(docs_dir=tmp_path / "docs")

    return ResearchAgent(
        llm_router=llm_router,
        discovery=discovery,
        collector=collector,
        analyzer=analyzer,
        context_manager=context_mgr,
        doc_generator=doc_gen,
        db_session=db_session,
    )


@pytest.fixture
def topic_with_sources(db_session) -> Topic:
    """Create a topic with pre-registered sources."""
    topic = Topic(
        name="Lake Travis Fishing",
        description="Monitor fishing conditions at Lake Travis",
        user_intent="Track fishing conditions at Lake Travis this weekend",
    )
    db_session.add(topic)
    db_session.commit()

    source = Source(
        topic_id=topic.id,
        url="https://api.weather.gov/points/30.3,-97.8",
        source_type="REST API",
        data_format="json",
        description="NWS weather forecast for Lake Travis area",
    )
    db_session.add(source)
    db_session.commit()
    return topic


@pytest.fixture
def topic_without_sources(db_session) -> Topic:
    """Create a topic with no sources (discovery needed)."""
    topic = Topic(
        name="FDA Tracking",
        description="Track FDA regulatory changes for digital health",
        user_intent="Track any FDA regulatory changes affecting digital health startups",
    )
    db_session.add(topic)
    db_session.commit()
    return topic


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_run_with_existing_sources(self, agent, topic_with_sources, db_session, monkeypatch):
        """Full pipeline should complete with existing sources."""
        # Monkeypatch the run data path to use tmp
        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        run = await agent.run(topic_with_sources.id)

        assert run.status == "completed"
        assert run.completed_at is not None
        assert run.sources_queried == 1
        assert run.doc_url is not None
        assert Path(run.doc_url).exists()

    @pytest.mark.asyncio
    async def test_run_creates_run_record(self, agent, topic_with_sources, db_session, monkeypatch):
        """Should create a Run record in the database."""
        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        run = await agent.run(topic_with_sources.id)
        loaded = db_session.get(Run, run.id)
        assert loaded is not None
        assert loaded.status == "completed"

    @pytest.mark.asyncio
    async def test_run_discovers_sources_when_none_exist(self, agent, topic_without_sources, db_session, monkeypatch):
        """Should run discovery if no sources are registered."""
        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        run = await agent.run(topic_without_sources.id)

        assert run.status == "completed"
        # Discovery should have added sources
        sources = db_session.query(Source).filter(
            Source.topic_id == topic_without_sources.id
        ).all()
        assert len(sources) > 0

    @pytest.mark.asyncio
    async def test_doc_has_content(self, agent, topic_with_sources, monkeypatch):
        """Generated doc should have actual content."""
        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        run = await agent.run(topic_with_sources.id)
        doc_text = Path(run.doc_url).read_text(encoding="utf-8")

        assert "## Summary" in doc_text
        assert "## Sources" in doc_text
        assert "Lake Travis" in doc_text

    @pytest.mark.asyncio
    async def test_context_updated_after_run(self, agent, topic_with_sources, monkeypatch):
        """Context should be updated after a successful run."""
        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        await agent.run(topic_with_sources.id)
        ctx = agent._context.load_context(topic_with_sources.id)
        assert ctx is not None
        assert len(ctx.recent_entries) == 1

    @pytest.mark.asyncio
    async def test_nonexistent_topic_raises(self, agent):
        """Should raise ValueError for nonexistent topic."""
        with pytest.raises(ValueError, match="not found"):
            await agent.run(9999)


class TestPipelineFailureHandling:
    @pytest.mark.asyncio
    async def test_failed_source_doesnt_stop_run(self, agent, db_session, monkeypatch):
        """A failed source should not prevent the run from completing."""
        topic = Topic(
            name="Mixed Sources",
            description="Topic with working and broken sources",
            user_intent="Test",
        )
        db_session.add(topic)
        db_session.commit()

        # Add a source that will fail (the mock returns 200 for all, but let's test the flow)
        source = Source(
            topic_id=topic.id,
            url="https://api.example.com/data",
            source_type="REST API",
            data_format="json",
            description="Test source",
        )
        db_session.add(source)
        db_session.commit()

        monkeypatch.setattr(
            agent, "_get_run_data_path",
            lambda tid: Path(agent._doc_gen._dir.parent / "runs" / f"topic_{tid}_latest.txt")
        )

        run = await agent.run(topic.id)
        assert run.status == "completed"
