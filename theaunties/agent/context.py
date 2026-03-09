"""Context manager — persistent per-topic context with rolling window."""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

ROLLING_WINDOW_DAYS = 7


@dataclass
class DailyEntry:
    """A single day's research entry in the context."""
    date: str
    findings_summary: str
    sources_used: list[str] = field(default_factory=list)
    changes_detected: list[str] = field(default_factory=list)
    raw_data_hash: str = ""


@dataclass
class TopicContext:
    """Full context for a research topic."""
    topic_id: int
    topic_name: str
    original_intent: str
    description: str
    key_aspects: list[str] = field(default_factory=list)
    user_clarifications: list[str] = field(default_factory=list)
    cumulative_summary: str = ""
    detected_trends: list[str] = field(default_factory=list)
    source_performance: dict = field(default_factory=dict)
    recent_entries: list[DailyEntry] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_prompt_context(self) -> str:
        """Format context for inclusion in LLM prompts."""
        parts = [
            f"Topic: {self.topic_name}",
            f"Intent: {self.original_intent}",
            f"Description: {self.description}",
        ]
        if self.key_aspects:
            parts.append(f"Key aspects: {', '.join(self.key_aspects)}")
        if self.user_clarifications:
            parts.append(f"User clarifications: {'; '.join(self.user_clarifications)}")
        if self.cumulative_summary:
            parts.append(f"Accumulated knowledge: {self.cumulative_summary}")
        if self.detected_trends:
            parts.append(f"Detected trends: {'; '.join(self.detected_trends)}")
        if self.recent_entries:
            parts.append("Recent findings:")
            for entry in self.recent_entries[-3:]:  # Last 3 days for prompt
                parts.append(f"  [{entry.date}] {entry.findings_summary}")
        return "\n".join(parts)


class ContextManager:
    """Manages persistent per-topic context files."""

    def __init__(self, context_dir: Path):
        self._dir = context_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _context_path(self, topic_id: int) -> Path:
        return self._dir / f"topic_{topic_id}.json"

    def create_context(
        self,
        topic_id: int,
        topic_name: str,
        original_intent: str,
        description: str,
        key_aspects: list[str] | None = None,
    ) -> TopicContext:
        """Create a new context file for a topic."""
        now = datetime.now(timezone.utc).isoformat()
        context = TopicContext(
            topic_id=topic_id,
            topic_name=topic_name,
            original_intent=original_intent,
            description=description,
            key_aspects=key_aspects or [],
            created_at=now,
            updated_at=now,
        )
        self._save(context)
        logger.info("Created context for topic %d: %s", topic_id, topic_name)
        return context

    def load_context(self, topic_id: int) -> TopicContext | None:
        """Load context for a topic. Returns None if not found."""
        path = self._context_path(topic_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TopicContext(
                topic_id=data["topic_id"],
                topic_name=data["topic_name"],
                original_intent=data["original_intent"],
                description=data["description"],
                key_aspects=data.get("key_aspects", []),
                user_clarifications=data.get("user_clarifications", []),
                cumulative_summary=data.get("cumulative_summary", ""),
                detected_trends=data.get("detected_trends", []),
                source_performance=data.get("source_performance", {}),
                recent_entries=[
                    DailyEntry(**e) for e in data.get("recent_entries", [])
                ],
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to load context for topic %d: %s", topic_id, e)
            return None

    def update_after_run(
        self,
        topic_id: int,
        findings_summary: str,
        sources_used: list[str],
        changes_detected: list[str],
        date: str | None = None,
    ) -> TopicContext | None:
        """Update context after a research run."""
        context = self.load_context(topic_id)
        if context is None:
            logger.error("Cannot update context for topic %d: not found", topic_id)
            return None

        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        entry = DailyEntry(
            date=date,
            findings_summary=findings_summary,
            sources_used=sources_used,
            changes_detected=changes_detected,
        )
        context.recent_entries.append(entry)

        # Rolling window: keep last ROLLING_WINDOW_DAYS entries in detail
        self._apply_rolling_window(context)

        context.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(context)
        return context

    def add_clarification(self, topic_id: int, clarification: str) -> TopicContext | None:
        """Add a user clarification to the context."""
        context = self.load_context(topic_id)
        if context is None:
            return None

        context.user_clarifications.append(clarification)
        context.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(context)
        return context

    def update_trends(self, topic_id: int, trends: list[str]) -> TopicContext | None:
        """Update detected trends in the context."""
        context = self.load_context(topic_id)
        if context is None:
            return None

        context.detected_trends = trends
        context.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(context)
        return context

    def _apply_rolling_window(self, context: TopicContext) -> None:
        """Keep recent entries in detail, compress older ones into cumulative summary."""
        if len(context.recent_entries) <= ROLLING_WINDOW_DAYS:
            return

        # Entries to compress (older than the window)
        to_compress = context.recent_entries[:-ROLLING_WINDOW_DAYS]
        context.recent_entries = context.recent_entries[-ROLLING_WINDOW_DAYS:]

        # Append compressed entries to cumulative summary
        compressed_parts = []
        for entry in to_compress:
            compressed_parts.append(f"[{entry.date}] {entry.findings_summary}")

        if compressed_parts:
            new_summary = "; ".join(compressed_parts)
            if context.cumulative_summary:
                context.cumulative_summary += "; " + new_summary
            else:
                context.cumulative_summary = new_summary

    def _save(self, context: TopicContext) -> None:
        """Save context to disk."""
        path = self._context_path(context.topic_id)
        data = asdict(context)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
