"""Tests for the document generator."""

from pathlib import Path

import pytest

from theaunties.output.gdrive import DocContent, LocalDocGenerator, SourceStatus


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    return tmp_path / "docs"


@pytest.fixture
def generator(docs_dir: Path) -> LocalDocGenerator:
    return LocalDocGenerator(docs_dir=docs_dir)


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


class TestLocalDocGenerator:
    @pytest.mark.asyncio
    async def test_creates_file(self, generator, sample_content):
        """Should create a Markdown file."""
        path = await generator.generate(sample_content)
        assert Path(path).exists()

    @pytest.mark.asyncio
    async def test_filename_convention(self, generator, sample_content):
        """File should follow the naming convention."""
        path = await generator.generate(sample_content)
        filename = Path(path).name
        assert "Lake_Travis_Fishing" in filename
        assert "Research Digest" in filename
        assert "2026-03-08" in filename
        assert filename.endswith(".md")

    @pytest.mark.asyncio
    async def test_contains_summary_section(self, generator, sample_content):
        """Doc should contain the Summary section."""
        path = await generator.generate(sample_content)
        text = Path(path).read_text(encoding="utf-8")
        assert "## Summary" in text
        assert "favorable" in text

    @pytest.mark.asyncio
    async def test_contains_changes_section(self, generator, sample_content):
        """Doc should contain the What Changed section."""
        path = await generator.generate(sample_content)
        text = Path(path).read_text(encoding="utf-8")
        assert "## What Changed" in text
        assert "62F → 65F" in text

    @pytest.mark.asyncio
    async def test_contains_findings_section(self, generator, sample_content):
        """Doc should contain the Detailed Findings section."""
        path = await generator.generate(sample_content)
        text = Path(path).read_text(encoding="utf-8")
        assert "## Detailed Findings" in text
        assert "USGS Water Services" in text

    @pytest.mark.asyncio
    async def test_contains_sources_section(self, generator, sample_content):
        """Doc should contain the Sources section with status table."""
        path = await generator.generate(sample_content)
        text = Path(path).read_text(encoding="utf-8")
        assert "## Sources" in text
        assert "waterservices.usgs.gov" in text
        assert "success" in text

    @pytest.mark.asyncio
    async def test_contains_agent_notes(self, generator, sample_content):
        """Doc should contain the Agent Notes section."""
        path = await generator.generate(sample_content)
        text = Path(path).read_text(encoding="utf-8")
        assert "## Agent Notes" in text
        assert "barometric pressure" in text

    @pytest.mark.asyncio
    async def test_empty_findings(self, generator):
        """Should handle empty findings gracefully."""
        content = DocContent(
            topic_name="Empty Test",
            date="2026-03-08",
            summary="No data collected.",
        )
        path = await generator.generate(content)
        text = Path(path).read_text(encoding="utf-8")
        assert "No findings to report" in text

    @pytest.mark.asyncio
    async def test_empty_changes(self, generator):
        """Should handle no changes gracefully."""
        content = DocContent(
            topic_name="No Changes",
            date="2026-03-08",
            summary="All stable.",
        )
        path = await generator.generate(content)
        text = Path(path).read_text(encoding="utf-8")
        assert "No changes detected" in text

    @pytest.mark.asyncio
    async def test_failed_source_shows_error(self, generator):
        """Failed sources should show error info."""
        content = DocContent(
            topic_name="Error Test",
            date="2026-03-08",
            summary="Partial data.",
            source_statuses=[
                SourceStatus(name="Broken API", url="https://api.broken.com", status="failed", error="HTTP 503"),
            ],
        )
        path = await generator.generate(content)
        text = Path(path).read_text(encoding="utf-8")
        assert "failed" in text
        assert "503" in text


class TestDocContentValidation:
    def test_valid_citations(self, sample_content):
        """Citations referencing known sources should pass."""
        issues = sample_content.validate_citations()
        assert len(issues) == 0

    def test_unknown_citation_flagged(self):
        """Citations not matching any source should be flagged."""
        content = DocContent(
            topic_name="Test",
            date="2026-03-08",
            summary="Test",
            findings=[{"source": "X", "text": "text", "citations": ["Unknown Source"]}],
            source_statuses=[
                SourceStatus(name="Known API", url="https://known.api.com", status="success"),
            ],
        )
        issues = content.validate_citations()
        assert len(issues) == 1
        assert "Unknown Source" in issues[0]
