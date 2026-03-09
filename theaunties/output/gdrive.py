"""Document generator — local stub and Google Drive implementations."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
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
    """Generates Google Docs via the Drive and Docs APIs.

    Requires:
        - A Google Cloud service account with the Drive API and Docs API enabled.
        - A JSON credentials file for the service account.
        - A Google Drive folder ID that is shared with the service account email.
        - A user email to share created docs with.

    Setup steps:
        1. Create a Google Cloud project and enable "Google Drive API" + "Google Docs API".
        2. Create a service account and download the JSON key file.
        3. Share your target Drive folder with the service account email (Editor access).
        4. Set GOOGLE_DRIVE_CREDENTIALS_PATH, GOOGLE_DRIVE_FOLDER_ID, and USER_EMAIL in .env.
        5. Set USE_STUBS=false in .env.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/documents",
    ]

    def __init__(self, credentials_path: str, folder_id: str, user_email: str):
        self._credentials_path = credentials_path
        self._folder_id = folder_id
        self._user_email = user_email
        self._drive_service = None
        self._docs_service = None

    def _get_services(self):
        """Lazy-initialize the Google API services (not async-safe, run in executor)."""
        if self._drive_service is None or self._docs_service is None:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                self._credentials_path, scopes=self.SCOPES
            )
            self._drive_service = build("drive", "v3", credentials=creds)
            self._docs_service = build("docs", "v1", credentials=creds)

        return self._drive_service, self._docs_service

    async def generate(self, content: DocContent) -> str:
        """Create a Google Doc with research findings and return its URL.

        The doc is created in the configured Drive folder and shared with the user.
        """
        loop = asyncio.get_event_loop()

        # Run all blocking Google API calls in a thread executor
        doc_url = await loop.run_in_executor(None, partial(self._generate_sync, content))
        return doc_url

    def _generate_sync(self, content: DocContent) -> str:
        """Synchronous implementation of doc generation (runs in thread executor)."""
        drive_service, docs_service = self._get_services()

        title = f"{content.topic_name} — Research Digest — {content.date}"

        # Step 1: Create a blank Google Doc in the target folder
        doc_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [self._folder_id],
        }
        created_file = drive_service.files().create(
            body=doc_metadata, fields="id,webViewLink"
        ).execute()

        doc_id = created_file["id"]
        doc_url = created_file["webViewLink"]

        logger.info("Created Google Doc: %s (%s)", title, doc_url)

        # Step 2: Build the document body with formatted content
        requests = self._build_doc_requests(content, title)
        if requests:
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

        # Step 3: Share the doc with the user
        if self._user_email:
            try:
                drive_service.permissions().create(
                    fileId=doc_id,
                    body={
                        "type": "user",
                        "role": "reader",
                        "emailAddress": self._user_email,
                    },
                    sendNotificationEmail=True,
                ).execute()
                logger.info("Shared doc with %s", self._user_email)
            except Exception as e:
                logger.warning("Failed to share doc with %s: %s", self._user_email, e)

        return doc_url

    def _build_doc_requests(self, content: DocContent, title: str) -> list[dict]:
        """Build Google Docs API batchUpdate requests to populate the doc.

        The Docs API inserts text at an index. We build requests in reverse order
        of where they appear so indices stay stable, OR we insert sequentially
        tracking the current index.
        """
        requests: list[dict] = []
        idx = 1  # Docs start with index 1 (after the implicit newline)

        # Helper to insert text and advance index
        def insert_text(text: str, bold: bool = False, heading: str | None = None,
                        font_size: int | None = None) -> None:
            nonlocal idx
            requests.append({
                "insertText": {
                    "location": {"index": idx},
                    "text": text,
                }
            })
            text_len = len(text)

            # Apply formatting
            if bold or font_size:
                style: dict = {}
                update_fields = []
                if bold:
                    style["bold"] = True
                    update_fields.append("bold")
                if font_size:
                    style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
                    update_fields.append("fontSize")
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": idx, "endIndex": idx + text_len},
                        "textStyle": style,
                        "fields": ",".join(update_fields),
                    }
                })

            if heading:
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": idx, "endIndex": idx + text_len},
                        "paragraphStyle": {"namedStyleType": heading},
                        "fields": "namedStyleType",
                    }
                })

            idx += text_len

        # --- Title ---
        insert_text(f"{title}\n", heading="HEADING_1")

        # --- Summary ---
        insert_text("\nSummary\n", heading="HEADING_2")
        summary_text = content.summary or "No summary available."
        insert_text(f"{summary_text}\n\n")

        # --- What Changed ---
        insert_text("What Changed\n", heading="HEADING_2")
        if content.changes:
            for change in content.changes:
                insert_text(f"• {change}\n")
            insert_text("\n")
        else:
            insert_text("No changes detected since last run.\n\n")

        # --- Detailed Findings ---
        insert_text("Detailed Findings\n", heading="HEADING_2")
        if content.findings:
            for finding in content.findings:
                source = finding.get("source", "Unknown")
                text = finding.get("text", "")
                insert_text(f"{source}\n", heading="HEADING_3")
                insert_text(f"{text}\n\n")
        else:
            insert_text("No findings to report.\n\n")

        # --- Sources ---
        insert_text("Sources\n", heading="HEADING_2")
        if content.source_statuses:
            # Build a simple text table (Google Docs doesn't have native tables via insertText)
            insert_text("Source | URL | Status | Last Checked\n", bold=True)
            for s in content.source_statuses:
                error_note = f" ({s.error})" if s.error else ""
                insert_text(f"{s.name} | {s.url} | {s.status}{error_note} | {s.last_checked}\n")
            insert_text("\n")
        else:
            insert_text("No sources registered.\n\n")

        # --- Agent Notes ---
        insert_text("Agent Notes\n", heading="HEADING_2")
        agent_text = content.agent_notes or "No notes."
        insert_text(f"{agent_text}\n")

        # --- Confidence Assessment (optional) ---
        if content.confidence_notes:
            insert_text("\nConfidence Assessment\n", heading="HEADING_3")
            insert_text(f"{content.confidence_notes}\n")

        return requests
