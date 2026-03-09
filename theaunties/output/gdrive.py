"""Document generator — local stub and Google Drive implementations."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SourceStatus:
    """Status of a data source for the daily doc."""
    name: str
    url: str
    status: str  # success, failed, timeout
    last_checked: str = ""
    error: str = ""


@dataclass
class DocContent:
    """Structured content for the daily research document."""
    topic_name: str
    date: str
    summary: str
    changes: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)  # [{source, text, citations}]
    source_statuses: list[SourceStatus] = field(default_factory=list)
    agent_notes: str = ""
    confidence_notes: str = ""

    def validate_citations(self) -> list[str]:
        """Check that all citations reference known sources. Returns list of issues."""
        known_sources = {s.name.lower() for s in self.source_statuses}
        known_urls = {s.url.lower() for s in self.source_statuses}
        issues = []
        for finding in self.findings:
            for citation in finding.get("citations", []):
                if citation.lower() not in known_sources and citation.lower() not in known_urls:
                    issues.append(f"Unknown citation: {citation}")
        return issues


class DocGenerator(ABC):
    """Base class for document generators."""

    @abstractmethod
    async def generate(self, content: DocContent) -> str:
        """Generate a document from structured content. Returns the doc location/URL."""
        ...


class LocalDocGenerator(DocGenerator):
    """Generates Markdown documents to the local filesystem.

    Used for development and testing. Swap to GoogleDriveDocGenerator for production.
    """

    def __init__(self, docs_dir: Path):
        self._dir = docs_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, content: DocContent) -> str:
        """Generate a Markdown file and return its path."""
        filename = self._make_filename(content.topic_name, content.date)
        path = self._dir / filename
        markdown = self._render_markdown(content)
        path.write_text(markdown, encoding="utf-8")
        logger.info("Generated local doc: %s", path)
        return str(path)

    def _make_filename(self, topic_name: str, date: str) -> str:
        """Generate filename following the naming convention."""
        safe_name = topic_name.replace(" ", "_").replace("/", "-")
        return f"{safe_name} — Research Digest — {date}.md"

    def _render_markdown(self, content: DocContent) -> str:
        """Render DocContent as Markdown."""
        lines = [
            f"# {content.topic_name} — Research Digest — {content.date}",
            "",
            "## Summary",
            "",
            content.summary or "_No summary available._",
            "",
            "## What Changed",
            "",
        ]

        if content.changes:
            for change in content.changes:
                lines.append(f"- {change}")
        else:
            lines.append("_No changes detected since last run._")

        lines.extend(["", "## Detailed Findings", ""])

        if content.findings:
            for finding in content.findings:
                source = finding.get("source", "Unknown")
                text = finding.get("text", "")
                lines.append(f"### {source}")
                lines.append("")
                lines.append(text)
                lines.append("")
        else:
            lines.append("_No findings to report._")

        lines.extend(["", "## Sources", ""])

        if content.source_statuses:
            lines.append("| Source | URL | Status | Last Checked |")
            lines.append("|--------|-----|--------|-------------|")
            for s in content.source_statuses:
                error_note = f" ({s.error})" if s.error else ""
                lines.append(f"| {s.name} | {s.url} | {s.status}{error_note} | {s.last_checked} |")
        else:
            lines.append("_No sources registered._")

        lines.extend(["", "## Agent Notes", ""])
        lines.append(content.agent_notes or "_No notes._")

        if content.confidence_notes:
            lines.extend(["", "### Confidence Assessment", "", content.confidence_notes])

        lines.append("")
        return "\n".join(lines)


class GoogleDriveDocGenerator(DocGenerator):
    """Generates Google Docs via the Drive API.

    Placeholder — activate by setting USE_STUBS=false.
    Requires: google-api-python-client, google-auth, service account credentials.
    """

    def __init__(self, credentials_path: str, folder_id: str, user_email: str):
        self._credentials_path = credentials_path
        self._folder_id = folder_id
        self._user_email = user_email

    async def generate(self, content: DocContent) -> str:
        raise NotImplementedError(
            "Google Drive doc generator not yet implemented. Set USE_STUBS=true in .env."
        )
