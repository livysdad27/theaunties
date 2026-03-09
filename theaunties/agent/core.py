"""Research agent core — orchestrates the full research pipeline."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from theaunties.agent.analyzer import Analyzer, AnalysisResult
from theaunties.agent.collector import CollectionSummary, DataCollector
from theaunties.agent.context import ContextManager, TopicContext
from theaunties.agent.discovery import SourceDiscovery
from theaunties.db.models import Run, Source, Topic
from theaunties.llm.router import LLMRouter, TaskType
from theaunties.output.gdrive import DocContent, DocGenerator, SourceStatus
from theaunties.prompts.synthesis import daily_doc_prompt

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Orchestrates a single research run for a topic.

    Pipeline: load context → discover sources (if needed) → collect data →
    analyze/detect changes → generate doc → update context → log run.
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        discovery: SourceDiscovery,
        collector: DataCollector,
        analyzer: Analyzer,
        context_manager: ContextManager,
        doc_generator: DocGenerator,
        db_session: Session,
    ):
        self._llm = llm_router
        self._discovery = discovery
        self._collector = collector
        self._analyzer = analyzer
        self._context = context_manager
        self._doc_gen = doc_generator
        self._db = db_session

    async def run(self, topic_id: int) -> Run:
        """Execute a full research run for the given topic.

        Returns the Run record with status and results.
        """
        # Load topic from DB
        topic = self._db.get(Topic, topic_id)
        if topic is None:
            raise ValueError(f"Topic {topic_id} not found")

        # Create run record
        run = Run(topic_id=topic_id, status="running")
        self._db.add(run)
        self._db.commit()

        try:
            # Step 1: Load or create context
            context = self._context.load_context(topic_id)
            if context is None:
                context = self._context.create_context(
                    topic_id=topic_id,
                    topic_name=topic.name,
                    original_intent=topic.user_intent,
                    description=topic.description,
                )

            # Step 2: Ensure we have sources (run discovery if none)
            sources = self._db.query(Source).filter(
                Source.topic_id == topic_id,
                Source.status == "active",
            ).all()

            if not sources:
                logger.info("No sources for topic %d, running discovery", topic_id)
                await self._run_discovery(topic)
                sources = self._db.query(Source).filter(
                    Source.topic_id == topic_id,
                    Source.status == "active",
                ).all()

            # Step 3: Collect data from sources
            source_dicts = [
                {"url": s.url, "data_format": s.data_format}
                for s in sources
            ]
            collection = await self._collector.collect_from_sources(source_dicts)

            # Step 4: Build combined data string for analysis
            current_data = self._format_collected_data(collection, sources)

            # Step 5: Load previous run data for comparison
            previous_data = self._get_previous_data(topic_id)

            # Step 6: Detect changes
            changes = await self._analyzer.detect_changes(
                topic_name=topic.name,
                previous_data=previous_data,
                current_data=current_data,
                context_summary=context.to_prompt_context(),
            )

            # Step 7: Summarize data
            source_metadata = "\n".join(
                f"- {s.description} ({s.url})" for s in sources
            )
            summary = await self._analyzer.summarize_data(
                topic_name=topic.name,
                collected_data=current_data,
                source_metadata=source_metadata,
            )

            # Step 8: Generate the daily doc
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            doc_content = self._build_doc_content(
                topic=topic,
                date=today,
                summary_text=summary.text,
                changes=changes,
                collection=collection,
                sources=sources,
            )
            doc_path = await self._doc_gen.generate(doc_content)

            # Step 9: Update context
            change_descriptions = [
                f"{c.field}: {c.previous_value} → {c.current_value}"
                for c in changes.changes
            ] if changes.changes else []

            self._context.update_after_run(
                topic_id=topic_id,
                findings_summary=summary.text[:500],
                sources_used=[s.url for s in sources],
                changes_detected=change_descriptions,
                date=today,
            )

            # Step 10: Store current data for next comparison
            self._store_run_data(topic_id, current_data)

            # Update run record
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.sources_queried = collection.total
            run.sources_failed = collection.failed
            run.doc_url = doc_path
            self._db.commit()

            logger.info(
                "Research run completed for topic %d: %d/%d sources, doc at %s",
                topic_id, collection.succeeded, collection.total, doc_path,
            )
            return run

        except Exception as e:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            self._db.commit()
            logger.error("Research run failed for topic %d: %s", topic_id, e)
            raise

    async def _run_discovery(self, topic: Topic) -> None:
        """Run source discovery for a topic and store results."""
        candidates = await self._discovery.brainstorm_sources(
            topic_name=topic.name,
            topic_description=topic.description,
        )

        for candidate in candidates:
            result = await self._discovery.validate_source(candidate.url)
            if hasattr(result, "sample_data"):  # ValidatedSource
                source = Source(
                    topic_id=topic.id,
                    url=result.url,
                    source_type=result.source_type,
                    data_format=result.data_format,
                    description=result.description,
                    status="active",
                    last_checked=datetime.now(timezone.utc),
                    last_success=datetime.now(timezone.utc),
                )
                self._db.add(source)
                logger.info("Discovered source: %s", result.url)
            else:
                logger.info("Rejected source: %s (%s)", result.url, result.reason)

        self._db.commit()

    def _format_collected_data(
        self, collection: CollectionSummary, sources: list[Source]
    ) -> str:
        """Format collected data into a string for analysis."""
        parts = []
        url_to_source = {s.url: s for s in sources}

        for result in collection.results:
            source = url_to_source.get(result.source_url)
            name = source.description if source else result.source_url

            if result.success:
                parts.append(f"[Source: {name}]\n{result.data[:5000]}\n")
            else:
                parts.append(f"[Source: {name}] FAILED: {result.error}\n")

        return "\n---\n".join(parts)

    def _get_previous_data(self, topic_id: int) -> str:
        """Get the data from the previous run for comparison."""
        data_file = self._get_run_data_path(topic_id)
        if data_file.exists():
            return data_file.read_text(encoding="utf-8")
        return ""

    def _store_run_data(self, topic_id: int, data: str) -> None:
        """Store run data for next comparison."""
        data_file = self._get_run_data_path(topic_id)
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text(data, encoding="utf-8")

    def _get_run_data_path(self, topic_id: int) -> Path:
        """Path to the stored run data file for a topic."""
        return Path("data") / "runs" / f"topic_{topic_id}_latest.txt"

    def _build_doc_content(
        self,
        topic: Topic,
        date: str,
        summary_text: str,
        changes: AnalysisResult,
        collection: CollectionSummary,
        sources: list[Source],
    ) -> DocContent:
        """Build DocContent from pipeline results."""
        # Format changes
        change_lines = []
        if changes.changes:
            for c in changes.changes:
                change_lines.append(
                    f"{c.field}: {c.previous_value} → {c.current_value} "
                    f"(Source: {c.source}) [{c.significance}]"
                )
        elif changes.no_changes:
            change_lines = []

        # Format findings
        findings = []
        url_to_source = {s.url: s for s in sources}
        for result in collection.results:
            if result.success:
                source = url_to_source.get(result.source_url)
                source_name = source.description if source else result.source_url
                findings.append({
                    "source": source_name,
                    "text": result.data[:2000],
                    "citations": [source_name],
                })

        # Format source statuses
        source_statuses = []
        for result in collection.results:
            source = url_to_source.get(result.source_url)
            source_statuses.append(SourceStatus(
                name=source.description if source else result.source_url,
                url=result.source_url,
                status="success" if result.success else "failed",
                last_checked=result.collected_at.isoformat(),
                error=result.error,
            ))

        return DocContent(
            topic_name=topic.name,
            date=date,
            summary=summary_text,
            changes=change_lines,
            findings=findings,
            source_statuses=source_statuses,
            agent_notes=changes.summary if changes.summary else "No additional notes.",
        )
