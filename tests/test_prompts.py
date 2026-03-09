"""Tests for prompt templates."""

from theaunties.prompts.analysis import change_detection_prompt, data_summary_prompt
from theaunties.prompts.chat import (
    qa_prompt,
    refinement_prompt,
    topic_confirmation_prompt,
    topic_parsing_prompt,
)
from theaunties.prompts.discovery import (
    source_brainstorm_prompt,
    source_validation_prompt,
    web_search_query_prompt,
)
from theaunties.prompts.synthesis import confidence_assessment_prompt, daily_doc_prompt


class TestDiscoveryPrompts:
    def test_brainstorm_includes_topic(self):
        prompt = source_brainstorm_prompt("Weather Tracking", "Monitor weather in Austin TX")
        assert "Weather Tracking" in prompt
        assert "Monitor weather in Austin TX" in prompt

    def test_brainstorm_excludes_existing_sources(self):
        prompt = source_brainstorm_prompt(
            "Weather", "Weather data",
            existing_sources=["https://api.weather.gov"]
        )
        assert "api.weather.gov" in prompt
        assert "do not suggest these again" in prompt.lower()

    def test_brainstorm_returns_nonempty(self):
        prompt = source_brainstorm_prompt("Test", "Test topic")
        assert len(prompt) > 100

    def test_validation_includes_url_and_sample(self):
        prompt = source_validation_prompt(
            "https://api.example.com/data",
            '{"temperature": 65, "unit": "F"}'
        )
        assert "api.example.com" in prompt
        assert "temperature" in prompt

    def test_validation_truncates_long_response(self):
        long_sample = "x" * 5000
        prompt = source_validation_prompt("https://example.com", long_sample)
        # The prompt should contain at most 2000 chars of the sample
        assert long_sample not in prompt

    def test_search_query_includes_topic(self):
        prompt = web_search_query_prompt("Lake Travis", "Fishing conditions at Lake Travis")
        assert "Lake Travis" in prompt
        assert "Fishing conditions" in prompt


class TestAnalysisPrompts:
    def test_change_detection_includes_both_datasets(self):
        prompt = change_detection_prompt(
            "Weather", "temp: 62F", "temp: 65F"
        )
        assert "62F" in prompt
        assert "65F" in prompt

    def test_change_detection_includes_context(self):
        prompt = change_detection_prompt(
            "Weather", "data1", "data2",
            context_summary="Tracking since March 1"
        )
        assert "Tracking since March 1" in prompt

    def test_change_detection_anti_hallucination(self):
        prompt = change_detection_prompt("Test", "a", "b")
        assert "do not infer" in prompt.lower() or "only report changes" in prompt.lower()

    def test_data_summary_includes_source_metadata(self):
        prompt = data_summary_prompt("Weather", "raw data here", "NWS API, USGS API")
        assert "NWS API" in prompt
        assert "raw data here" in prompt


class TestSynthesisPrompts:
    def test_daily_doc_includes_all_sections(self):
        prompt = daily_doc_prompt(
            topic_name="Weather",
            date="2026-03-08",
            summary_data="temp: 65F",
            changes="temp up 3 degrees",
            source_statuses="NWS: success",
        )
        assert "## Summary" in prompt
        assert "## What Changed" in prompt
        assert "## Detailed Findings" in prompt
        assert "## Sources" in prompt
        assert "## Agent Notes" in prompt

    def test_daily_doc_anti_hallucination_rules(self):
        prompt = daily_doc_prompt(
            topic_name="Test",
            date="2026-03-08",
            summary_data="data",
            changes="none",
            source_statuses="ok",
        )
        lower = prompt.lower()
        assert "never invent" in lower or "never" in lower
        assert "citation" in lower or "cite" in lower
        assert "hallucinate" in lower or "speculating" in lower

    def test_daily_doc_includes_context_when_provided(self):
        prompt = daily_doc_prompt(
            topic_name="Test",
            date="2026-03-08",
            summary_data="data",
            changes="none",
            source_statuses="ok",
            context_summary="Prior research shows upward trend",
        )
        assert "Prior research shows upward trend" in prompt

    def test_confidence_assessment_includes_findings(self):
        prompt = confidence_assessment_prompt("Water temp is 65F", source_count=3)
        assert "Water temp is 65F" in prompt
        assert "3" in prompt


class TestChatPrompts:
    def test_topic_parsing_includes_user_message(self):
        prompt = topic_parsing_prompt("Track weather at Lake Travis for fishing")
        assert "Track weather at Lake Travis" in prompt

    def test_topic_parsing_returns_nonempty(self):
        prompt = topic_parsing_prompt("Some topic")
        assert len(prompt) > 50

    def test_confirmation_includes_aspects(self):
        prompt = topic_confirmation_prompt(
            "Lake Travis Fishing",
            "Monitor fishing conditions",
            ["water temperature", "wind speed", "water level"],
        )
        assert "water temperature" in prompt
        assert "wind speed" in prompt

    def test_refinement_includes_history(self):
        history = [
            {"role": "user", "message": "Track fishing conditions"},
            {"role": "assistant", "message": "I'll track that for you"},
        ]
        prompt = refinement_prompt(
            "Focus more on water temperature",
            "Lake Travis Fishing",
            "Fishing conditions",
            "Current context",
            chat_history=history,
        )
        assert "Focus more on water temperature" in prompt
        assert "Track fishing conditions" in prompt

    def test_refinement_without_history(self):
        prompt = refinement_prompt(
            "Change something",
            "Topic",
            "Description",
            "Context",
        )
        assert "Change something" in prompt
        assert "CHAT HISTORY" not in prompt

    def test_qa_includes_question_and_data(self):
        prompt = qa_prompt(
            "What's the current water temperature?",
            "Lake Travis Fishing",
            "Water temp: 65F",
            "Been tracking since March 1",
            "NWS API, USGS API",
        )
        assert "water temperature" in prompt.lower()
        assert "65F" in prompt
        assert "NWS API" in prompt

    def test_qa_anti_hallucination(self):
        prompt = qa_prompt("question", "topic", "findings", "context", "sources")
        lower = prompt.lower()
        assert "only" in lower or "don't know" in lower
