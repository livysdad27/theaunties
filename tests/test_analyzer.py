"""Tests for the analyzer module."""

import pytest

from theaunties.agent.analyzer import Analyzer, AnalysisResult, Change, DataSummary
from theaunties.llm.claude import ClaudeStubClient
from theaunties.llm.gemini import GeminiStubClient
from theaunties.llm.router import LLMRouter


@pytest.fixture
def llm_router():
    return LLMRouter(
        gemini_client=GeminiStubClient(),
        claude_client=ClaudeStubClient(),
    )


@pytest.fixture
def analyzer(llm_router):
    return Analyzer(llm_router=llm_router)


class TestChangeDetection:
    @pytest.mark.asyncio
    async def test_first_run_no_previous(self, analyzer):
        """First run should report no changes (no previous data)."""
        result = await analyzer.detect_changes(
            topic_name="Weather",
            previous_data="",
            current_data='{"temp": 65}',
        )
        assert result.no_changes is True
        assert "first run" in result.summary.lower() or "no previous" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_identical_data_no_changes(self, analyzer):
        """Identical data should report no changes."""
        data = '{"temp": 65, "wind": 10}'
        result = await analyzer.detect_changes(
            topic_name="Weather",
            previous_data=data,
            current_data=data,
        )
        assert result.no_changes is True

    @pytest.mark.asyncio
    async def test_different_data_detects_changes(self, analyzer):
        """Different data should use LLM to analyze changes."""
        result = await analyzer.detect_changes(
            topic_name="Weather",
            previous_data='{"temp": 62}',
            current_data='{"temp": 65}',
        )
        # The stub returns change analysis text
        assert result.raw_analysis != "" or result.summary != ""

    @pytest.mark.asyncio
    async def test_with_context_summary(self, analyzer):
        """Should include context in analysis when provided."""
        result = await analyzer.detect_changes(
            topic_name="Weather",
            previous_data='{"temp": 62}',
            current_data='{"temp": 65}',
            context_summary="Tracking since March 1, temps rising",
        )
        assert isinstance(result, AnalysisResult)


class TestDataSummary:
    @pytest.mark.asyncio
    async def test_summarize_returns_text(self, analyzer):
        """Should return a text summary of collected data."""
        summary = await analyzer.summarize_data(
            topic_name="Weather",
            collected_data='{"temperature": 65, "wind_speed": 10}',
            source_metadata="NWS API: weather.gov, USGS: waterservices.usgs.gov",
        )
        assert isinstance(summary, DataSummary)
        assert summary.text != ""


class TestChangeDataclass:
    def test_change_fields(self):
        c = Change(
            field="temperature",
            previous_value="62F",
            current_value="65F",
            source="NWS API",
            significance="medium",
            explanation="Notable increase",
        )
        assert c.field == "temperature"
        assert c.significance == "medium"

    def test_change_defaults(self):
        c = Change(field="x", previous_value="a", current_value="b", source="s")
        assert c.significance == "medium"
        assert c.explanation == ""


class TestAnalysisResultDataclass:
    def test_empty_result(self):
        r = AnalysisResult()
        assert r.changes == []
        assert r.no_changes is False
        assert r.summary == ""

    def test_result_with_changes(self):
        r = AnalysisResult(
            changes=[Change("temp", "62", "65", "NWS")],
            summary="Temperature increased",
            no_changes=False,
        )
        assert len(r.changes) == 1
        assert r.summary == "Temperature increased"


class TestParseChanges:
    def test_parse_valid_json(self, analyzer):
        """Should parse well-formed JSON change output."""
        json_text = '''{
            "changes": [
                {"field": "temp", "previous_value": "62", "current_value": "65", "source": "NWS", "significance": "high", "explanation": "Rising"}
            ],
            "summary": "Temperature increased",
            "no_changes": false
        }'''
        result = analyzer._parse_changes(json_text)
        assert len(result.changes) == 1
        assert result.changes[0].field == "temp"
        assert result.summary == "Temperature increased"

    def test_parse_invalid_json_fallback(self, analyzer):
        """Should fallback to raw text when JSON is invalid."""
        result = analyzer._parse_changes("Some non-JSON analysis text here")
        assert result.raw_analysis == "Some non-JSON analysis text here"
        assert result.summary != ""
