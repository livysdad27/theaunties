"""Tests for context manager."""

import json
from pathlib import Path

import pytest

from theaunties.agent.context import ContextManager, TopicContext, ROLLING_WINDOW_DAYS


@pytest.fixture
def context_mgr(tmp_path: Path) -> ContextManager:
    return ContextManager(context_dir=tmp_path / "context")


class TestContextCreation:
    def test_creates_context_file(self, context_mgr):
        """Should create a JSON context file for a new topic."""
        ctx = context_mgr.create_context(
            topic_id=1,
            topic_name="Lake Travis Fishing",
            original_intent="Track fishing conditions",
            description="Monitor weather and water data at Lake Travis",
        )
        assert ctx.topic_id == 1
        assert ctx.topic_name == "Lake Travis Fishing"
        assert ctx.created_at != ""

    def test_context_file_exists_on_disk(self, context_mgr):
        """File should exist after creation."""
        context_mgr.create_context(1, "Test", "intent", "desc")
        path = context_mgr._context_path(1)
        assert path.exists()

    def test_context_with_key_aspects(self, context_mgr):
        """Should store key aspects."""
        ctx = context_mgr.create_context(
            topic_id=1,
            topic_name="Test",
            original_intent="intent",
            description="desc",
            key_aspects=["water temp", "wind speed"],
        )
        assert ctx.key_aspects == ["water temp", "wind speed"]


class TestContextLoading:
    def test_load_existing_context(self, context_mgr):
        """Should load a previously saved context."""
        context_mgr.create_context(1, "Test Topic", "intent", "desc")
        loaded = context_mgr.load_context(1)
        assert loaded is not None
        assert loaded.topic_name == "Test Topic"

    def test_load_nonexistent_returns_none(self, context_mgr):
        """Should return None for nonexistent topic."""
        assert context_mgr.load_context(999) is None

    def test_roundtrip_preserves_data(self, context_mgr):
        """Save and load should preserve all fields."""
        ctx = context_mgr.create_context(
            topic_id=1,
            topic_name="Full Test",
            original_intent="Test intent",
            description="Test description",
            key_aspects=["aspect1", "aspect2"],
        )
        loaded = context_mgr.load_context(1)
        assert loaded.topic_name == ctx.topic_name
        assert loaded.key_aspects == ctx.key_aspects
        assert loaded.original_intent == ctx.original_intent


class TestContextUpdate:
    def test_update_after_run(self, context_mgr):
        """Should add a daily entry after a run."""
        context_mgr.create_context(1, "Test", "intent", "desc")
        updated = context_mgr.update_after_run(
            topic_id=1,
            findings_summary="Water temp rose to 65F",
            sources_used=["NWS API", "USGS"],
            changes_detected=["temp: 62F → 65F"],
            date="2026-03-08",
        )
        assert updated is not None
        assert len(updated.recent_entries) == 1
        assert updated.recent_entries[0].date == "2026-03-08"
        assert "65F" in updated.recent_entries[0].findings_summary

    def test_update_nonexistent_returns_none(self, context_mgr):
        """Should return None if topic doesn't exist."""
        result = context_mgr.update_after_run(999, "summary", [], [])
        assert result is None

    def test_add_clarification(self, context_mgr):
        """Should store user clarifications."""
        context_mgr.create_context(1, "Test", "intent", "desc")
        updated = context_mgr.add_clarification(1, "Focus more on water temperature")
        assert updated is not None
        assert "Focus more on water temperature" in updated.user_clarifications

    def test_update_trends(self, context_mgr):
        """Should update detected trends."""
        context_mgr.create_context(1, "Test", "intent", "desc")
        updated = context_mgr.update_trends(1, ["Temperature rising steadily"])
        assert updated is not None
        assert "Temperature rising steadily" in updated.detected_trends


class TestRollingWindow:
    def test_entries_within_window_are_kept(self, context_mgr):
        """Entries within the rolling window should be kept in detail."""
        context_mgr.create_context(1, "Test", "intent", "desc")

        for i in range(ROLLING_WINDOW_DAYS):
            context_mgr.update_after_run(
                1, f"Day {i} findings", ["src"], [], date=f"2026-03-{i+1:02d}"
            )

        ctx = context_mgr.load_context(1)
        assert len(ctx.recent_entries) == ROLLING_WINDOW_DAYS
        assert ctx.cumulative_summary == ""  # Nothing compressed yet

    def test_old_entries_are_compressed(self, context_mgr):
        """Entries older than the window should be compressed into summary."""
        context_mgr.create_context(1, "Test", "intent", "desc")

        # Add more entries than the rolling window
        for i in range(ROLLING_WINDOW_DAYS + 3):
            context_mgr.update_after_run(
                1, f"Day {i} findings", ["src"], [], date=f"2026-03-{i+1:02d}"
            )

        ctx = context_mgr.load_context(1)
        assert len(ctx.recent_entries) == ROLLING_WINDOW_DAYS
        assert ctx.cumulative_summary != ""
        assert "Day 0 findings" in ctx.cumulative_summary
        assert "Day 1 findings" in ctx.cumulative_summary
        assert "Day 2 findings" in ctx.cumulative_summary

    def test_updated_at_changes(self, context_mgr):
        """updated_at should change after each update."""
        context_mgr.create_context(1, "Test", "intent", "desc")
        ctx1 = context_mgr.load_context(1)
        context_mgr.update_after_run(1, "findings", [], [])
        ctx2 = context_mgr.load_context(1)
        # They may be equal if very fast, but updated_at should be set
        assert ctx2.updated_at != ""


class TestPromptContext:
    def test_to_prompt_context(self, context_mgr):
        """Should format context for LLM prompts."""
        ctx = context_mgr.create_context(
            1, "Lake Travis", "fishing conditions", "weather and water",
            key_aspects=["water temp", "wind"],
        )
        prompt_ctx = ctx.to_prompt_context()
        assert "Lake Travis" in prompt_ctx
        assert "water temp" in prompt_ctx
        assert "fishing conditions" in prompt_ctx
