"""Tests for configuration loading."""

from pathlib import Path

from theaunties.config import Settings, get_settings


class TestSettings:
    def test_defaults(self):
        """Settings should have sensible defaults."""
        s = Settings(
            gemini_api_key="test",
            anthropic_api_key="test",
            web_search_api_key="test",
        )
        assert s.use_stubs is True
        assert s.default_schedule == "0 6 * * *"
        assert s.log_level == "INFO"
        assert s.llm_discovery_model == "gemini-3.1-pro-preview"
        assert s.llm_synthesis_model == "claude-sonnet-4-6"
        assert s.web_search_provider == "brave"

    def test_data_paths_are_path_objects(self):
        """Data directory settings should be Path objects."""
        s = Settings(
            gemini_api_key="test",
            anthropic_api_key="test",
            web_search_api_key="test",
        )
        assert isinstance(s.data_dir, Path)
        assert isinstance(s.db_path, Path)
        assert isinstance(s.context_dir, Path)
        assert isinstance(s.docs_dir, Path)

    def test_get_settings_with_overrides(self):
        """get_settings should accept keyword overrides."""
        s = get_settings(
            gemini_api_key="override-key",
            anthropic_api_key="test",
            web_search_api_key="test",
            log_level="DEBUG",
        )
        assert s.gemini_api_key == "override-key"
        assert s.log_level == "DEBUG"

    def test_stubs_default_true(self):
        """USE_STUBS should default to True for development."""
        s = Settings(
            gemini_api_key="test",
            anthropic_api_key="test",
            web_search_api_key="test",
        )
        assert s.use_stubs is True
