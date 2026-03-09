"""FastAPI application entry point for theAunties."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from theaunties.agent.analyzer import Analyzer
from theaunties.agent.collector import DataCollector
from theaunties.agent.context import ContextManager
from theaunties.agent.core import ResearchAgent
from theaunties.agent.discovery import SourceDiscovery, WebSearchStub
from theaunties.chat.handler import ChatHandler
from theaunties.config import get_settings
from theaunties.db.database import get_engine, get_session_factory, init_db
from theaunties.db.models import Run, Source, Topic
from theaunties.llm.claude import ClaudeStubClient
from theaunties.llm.gemini import GeminiStubClient
from theaunties.llm.router import LLMRouter
from theaunties.output.gdrive import LocalDocGenerator
from theaunties.scheduler.manager import SchedulerManager

logger = logging.getLogger(__name__)

# --- App state (initialized in lifespan) ---
_state: dict = {}


def _build_components(settings=None):
    """Build all application components. Returns a dict of components."""
    settings = settings or get_settings()

    # Database
    engine = get_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    # LLM
    if settings.use_stubs:
        gemini = GeminiStubClient(model=settings.llm_discovery_model)
        claude = ClaudeStubClient(model=settings.llm_synthesis_model)
    else:
        from theaunties.llm.gemini import GeminiClient
        from theaunties.llm.claude import ClaudeClient
        gemini = GeminiClient(api_key=settings.gemini_api_key, model=settings.llm_discovery_model)
        claude = ClaudeClient(api_key=settings.anthropic_api_key, model=settings.llm_synthesis_model)

    llm_router = LLMRouter(gemini_client=gemini, claude_client=claude)

    # Agent components
    http_client = httpx.AsyncClient(timeout=15.0)
    discovery = SourceDiscovery(llm_router=llm_router, web_search=WebSearchStub(), http_client=http_client)
    collector = DataCollector(http_client=http_client)
    analyzer = Analyzer(llm_router=llm_router)
    context_mgr = ContextManager(context_dir=settings.context_dir)
    doc_gen = LocalDocGenerator(docs_dir=settings.docs_dir)

    return {
        "settings": settings,
        "engine": engine,
        "session_factory": session_factory,
        "llm_router": llm_router,
        "http_client": http_client,
        "discovery": discovery,
        "collector": collector,
        "analyzer": analyzer,
        "context_mgr": context_mgr,
        "doc_gen": doc_gen,
    }


def _make_agent(components: dict, db_session: Session) -> ResearchAgent:
    """Create a ResearchAgent from components."""
    return ResearchAgent(
        llm_router=components["llm_router"],
        discovery=components["discovery"],
        collector=components["collector"],
        analyzer=components["analyzer"],
        context_manager=components["context_mgr"],
        doc_generator=components["doc_gen"],
        db_session=db_session,
    )


async def _run_topic(topic_id: int) -> None:
    """Callback for scheduled runs."""
    components = _state["components"]
    session = components["session_factory"]()
    try:
        agent = _make_agent(components, session)
        await agent.run(topic_id)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    components = _build_components()
    _state["components"] = components

    # Start scheduler
    scheduler = SchedulerManager(run_callback=_run_topic)
    scheduler.start()
    _state["scheduler"] = scheduler

    # Schedule all existing active topics
    session = components["session_factory"]()
    try:
        topics = session.query(Topic).filter(Topic.status == "active").all()
        for topic in topics:
            scheduler.add_topic(topic.id, topic.schedule)
    finally:
        session.close()

    # Create chat handler
    session = components["session_factory"]()
    chat_handler = ChatHandler(
        llm_router=components["llm_router"],
        context_manager=components["context_mgr"],
        db_session=session,
    )
    _state["chat_handler"] = chat_handler
    _state["chat_session"] = session

    logger.info("theAunties started (stubs=%s)", components["settings"].use_stubs)
    yield

    # Shutdown
    scheduler.shutdown()
    await components["http_client"].aclose()
    _state.get("chat_session", session).close()
    logger.info("theAunties shut down")


app = FastAPI(
    title="theAunties",
    description="Autonomous research agents that watch the world so you don't have to",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Request/Response models ---

class ChatRequest(BaseModel):
    message: str


class ChatResponseModel(BaseModel):
    message: str
    topic_id: int | None = None
    state: str
    action: str


class TopicResponse(BaseModel):
    id: int
    name: str
    description: str
    status: str
    schedule: str


class TopicStatusResponse(BaseModel):
    id: int
    name: str
    status: str
    source_count: int
    last_run_status: str | None
    last_run_at: str | None
    next_run_at: str | None


# --- Endpoints ---

@app.post("/chat", response_model=ChatResponseModel)
async def chat(request: ChatRequest):
    """Send a chat message."""
    handler: ChatHandler = _state["chat_handler"]
    response = await handler.handle_message(request.message)

    # If a topic was just created, schedule it
    if response.action == "created" and response.topic_id:
        session = _state["components"]["session_factory"]()
        try:
            topic = session.get(Topic, response.topic_id)
            if topic:
                _state["scheduler"].add_topic(topic.id, topic.schedule)
        finally:
            session.close()

    return ChatResponseModel(
        message=response.message,
        topic_id=response.topic_id,
        state=response.state.value,
        action=response.action,
    )


@app.get("/topics", response_model=list[TopicResponse])
async def list_topics():
    """List all topics."""
    session = _state["components"]["session_factory"]()
    try:
        topics = session.query(Topic).all()
        return [
            TopicResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                status=t.status,
                schedule=t.schedule,
            )
            for t in topics
        ]
    finally:
        session.close()


@app.get("/topics/{topic_id}/status", response_model=TopicStatusResponse)
async def topic_status(topic_id: int):
    """Get status of a specific topic."""
    session = _state["components"]["session_factory"]()
    try:
        topic = session.get(Topic, topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        source_count = session.query(Source).filter(Source.topic_id == topic_id).count()

        last_run = (
            session.query(Run)
            .filter(Run.topic_id == topic_id)
            .order_by(Run.started_at.desc())
            .first()
        )

        next_run = _state["scheduler"].get_next_run(topic_id)

        return TopicStatusResponse(
            id=topic.id,
            name=topic.name,
            status=topic.status,
            source_count=source_count,
            last_run_status=last_run.status if last_run else None,
            last_run_at=last_run.started_at.isoformat() if last_run and last_run.started_at else None,
            next_run_at=next_run.isoformat() if next_run else None,
        )
    finally:
        session.close()


@app.post("/topics/{topic_id}/run")
async def trigger_run(topic_id: int):
    """Trigger an immediate research run for a topic."""
    session = _state["components"]["session_factory"]()
    try:
        topic = session.get(Topic, topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
    finally:
        session.close()

    await _run_topic(topic_id)
    return {"status": "completed", "topic_id": topic_id}
