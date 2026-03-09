"""Tests for the GoogleDriveDocGenerator (mocked — no real API calls)."""

from unittest.mock import MagicMock, patch, call

import pytest

from theaunties.output.gdrive import DocContent, GoogleDriveDocGenerator, SourceStatus


@pytest.fixture
def sample_content() -> DocContent:
    return DocContent(
        topic_name="Lake Travis Fishing",
        date="2026-03-08",
        summary="Conditions at Lake Travis remain favorable. Water temperature has risen to 65F.",
        changes=[
            "Water temperature: 62F → 65F (Source: USGS Water Services)",
            "Wind speed: 15mph → 8mph (Source: NWS API)",
        ],
        findings=[
            {
                "source": "USGS Water Services",
                "text": "Water temperature at gauge 08154700 reads 65F as of 06:00 CST [Source: USGS Water Services].",
                "citations": ["USGS Water Services"],
            },
            {
                "source": "NWS API",
                "text": "Wind speed forecast shows 8mph from the south [Source: NWS API].",
                "citations": ["NWS API"],
            },
        ],
        source_statuses=[
            SourceStatus(name="USGS Water Services", url="https://waterservices.usgs.gov", status="success", last_checked="2026-03-08T06:00:00Z"),
            SourceStatus(name="NWS API", url="https://api.weather.gov", status="success", last_checked="2026-03-08T06:00:00Z"),
        ],
        agent_notes="All sources responding normally. Consider adding barometric pressure data.",
    )


@pytest.fixture
def empty_content() -> DocContent:
    return DocContent(
        topic_name="Empty Test",
        date="2026-03-08",
        summary="No data collected.",
    )


def _make_mock_services():
    """Create mock Drive and Docs services."""
    mock_drive = MagicMock()
    mock_docs = MagicMock()

    # Drive files().create() returns an id and webViewLink
    mock_drive.files.return_value.create.return_value.execute.return_value = {
        "id": "doc_abc123",
        "webViewLink": "https://docs.google.com/document/d/doc_abc123/edit",
    }

    # Drive permissions().create() succeeds
    mock_drive.permissions.return_value.create.return_value.execute.return_value = {"id": "perm_1"}

    # Docs batchUpdate succeeds
    mock_docs.documents.return_value.batchUpdate.return_value.execute.return_value = {}

    return mock_drive, mock_docs


@pytest.fixture
def generator():
    """Create a GoogleDriveDocGenerator with mocked services."""
    gen = GoogleDriveDocGenerator(
        credentials_path="/fake/credentials.json",
        folder_id="folder_xyz",
        user_email="user@example.com",
    )
    mock_drive, mock_docs = _make_mock_services()
    gen._drive_service = mock_drive
    gen._docs_service = mock_docs
    return gen


class TestGoogleDriveDocGenerator:
    @pytest.mark.asyncio
    async def test_generate_returns_doc_url(self, generator, sample_content):
        """Should return the Google Doc URL."""
        url = await generator.generate(sample_content)
        assert url == "https://docs.google.com/document/d/doc_abc123/edit"

    @pytest.mark.asyncio
    async def test_creates_doc_in_target_folder(self, generator, sample_content):
        """Should create the doc in the configured Drive folder."""
        await generator.generate(sample_content)

        create_call = generator._drive_service.files.return_value.create
        create_call.assert_called_once()
        body = create_call.call_args[1]["body"]
        assert body["parents"] == ["folder_xyz"]
        assert body["mimeType"] == "application/vnd.google-apps.document"

    @pytest.mark.asyncio
    async def test_doc_title_follows_convention(self, generator, sample_content):
        """Doc title should follow the naming convention."""
        await generator.generate(sample_content)

        create_call = generator._drive_service.files.return_value.create
        body = create_call.call_args[1]["body"]
        assert "Lake Travis Fishing" in body["name"]
        assert "Research Digest" in body["name"]
        assert "2026-03-08" in body["name"]

    @pytest.mark.asyncio
    async def test_shares_doc_with_user(self, generator, sample_content):
        """Should share the doc with the configured user email."""
        await generator.generate(sample_content)

        perm_create = generator._drive_service.permissions.return_value.create
        perm_create.assert_called_once()
        perm_body = perm_create.call_args[1]["body"]
        assert perm_body["emailAddress"] == "user@example.com"
        assert perm_body["role"] == "reader"
        assert perm_body["type"] == "user"

    @pytest.mark.asyncio
    async def test_batch_update_called_with_requests(self, generator, sample_content):
        """Should populate the doc with batchUpdate requests."""
        await generator.generate(sample_content)

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        batch_update.assert_called_once()
        call_kwargs = batch_update.call_args[1]
        assert call_kwargs["documentId"] == "doc_abc123"
        body = call_kwargs["body"]
        assert "requests" in body
        assert len(body["requests"]) > 0

    @pytest.mark.asyncio
    async def test_requests_contain_all_sections(self, generator, sample_content):
        """batchUpdate requests should contain all document sections."""
        await generator.generate(sample_content)

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        body = batch_update.call_args[1]["body"]
        # Collect all inserted text
        all_text = ""
        for req in body["requests"]:
            if "insertText" in req:
                all_text += req["insertText"]["text"]

        assert "Summary" in all_text
        assert "What Changed" in all_text
        assert "Detailed Findings" in all_text
        assert "Sources" in all_text
        assert "Agent Notes" in all_text

    @pytest.mark.asyncio
    async def test_requests_contain_findings_content(self, generator, sample_content):
        """batchUpdate should include actual findings data."""
        await generator.generate(sample_content)

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        body = batch_update.call_args[1]["body"]
        all_text = ""
        for req in body["requests"]:
            if "insertText" in req:
                all_text += req["insertText"]["text"]

        assert "USGS Water Services" in all_text
        assert "NWS API" in all_text
        assert "65F" in all_text

    @pytest.mark.asyncio
    async def test_requests_contain_changes(self, generator, sample_content):
        """batchUpdate should include change bullets."""
        await generator.generate(sample_content)

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        body = batch_update.call_args[1]["body"]
        all_text = ""
        for req in body["requests"]:
            if "insertText" in req:
                all_text += req["insertText"]["text"]

        assert "62F → 65F" in all_text
        assert "15mph → 8mph" in all_text

    @pytest.mark.asyncio
    async def test_empty_content_handled(self, generator, empty_content):
        """Should handle empty findings/changes gracefully."""
        url = await generator.generate(empty_content)
        assert "docs.google.com" in url

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        body = batch_update.call_args[1]["body"]
        all_text = ""
        for req in body["requests"]:
            if "insertText" in req:
                all_text += req["insertText"]["text"]

        assert "No changes detected" in all_text
        assert "No findings to report" in all_text

    @pytest.mark.asyncio
    async def test_share_failure_does_not_crash(self, generator, sample_content):
        """If sharing fails, the doc should still be generated."""
        generator._drive_service.permissions.return_value.create.return_value.execute.side_effect = (
            Exception("Permission denied")
        )
        # Should not raise
        url = await generator.generate(sample_content)
        assert url == "https://docs.google.com/document/d/doc_abc123/edit"

    @pytest.mark.asyncio
    async def test_no_share_when_no_email(self, sample_content):
        """Should skip sharing when no user_email is configured."""
        gen = GoogleDriveDocGenerator(
            credentials_path="/fake/credentials.json",
            folder_id="folder_xyz",
            user_email="",
        )
        mock_drive, mock_docs = _make_mock_services()
        gen._drive_service = mock_drive
        gen._docs_service = mock_docs

        await gen.generate(sample_content)
        mock_drive.permissions.return_value.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_confidence_notes_included(self, generator):
        """Confidence notes should appear in the doc when provided."""
        content = DocContent(
            topic_name="Test",
            date="2026-03-08",
            summary="Test summary",
            confidence_notes="High confidence — all sources responded successfully.",
        )
        await generator.generate(content)

        batch_update = generator._docs_service.documents.return_value.batchUpdate
        body = batch_update.call_args[1]["body"]
        all_text = ""
        for req in body["requests"]:
            if "insertText" in req:
                all_text += req["insertText"]["text"]

        assert "Confidence Assessment" in all_text
        assert "High confidence" in all_text


class TestBuildDocRequests:
    """Test the _build_doc_requests method directly."""

    def test_returns_list_of_requests(self, generator, sample_content):
        """Should return a non-empty list of API requests."""
        requests = generator._build_doc_requests(sample_content, "Test Title")
        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_first_request_is_title(self, generator, sample_content):
        """First insertText should be the document title."""
        requests = generator._build_doc_requests(sample_content, "My Title")
        first_insert = next(r for r in requests if "insertText" in r)
        assert "My Title" in first_insert["insertText"]["text"]

    def test_headings_applied(self, generator, sample_content):
        """Should apply heading styles to section headers."""
        requests = generator._build_doc_requests(sample_content, "Test Title")
        heading_requests = [r for r in requests if "updateParagraphStyle" in r]
        heading_types = {r["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
                         for r in heading_requests}
        assert "HEADING_1" in heading_types
        assert "HEADING_2" in heading_types

    def test_source_statuses_included(self, generator, sample_content):
        """Source status table should be in the requests."""
        requests = generator._build_doc_requests(sample_content, "Test Title")
        all_text = "".join(
            r["insertText"]["text"] for r in requests if "insertText" in r
        )
        assert "waterservices.usgs.gov" in all_text
        assert "api.weather.gov" in all_text
        assert "success" in all_text

    def test_failed_source_shows_error(self, generator):
        """Failed sources should show error details."""
        content = DocContent(
            topic_name="Error Test",
            date="2026-03-08",
            summary="Partial data.",
            source_statuses=[
                SourceStatus(name="Broken API", url="https://api.broken.com",
                             status="failed", error="HTTP 503"),
            ],
        )
        requests = generator._build_doc_requests(content, "Test Title")
        all_text = "".join(
            r["insertText"]["text"] for r in requests if "insertText" in r
        )
        assert "failed" in all_text
        assert "503" in all_text
