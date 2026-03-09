"""Configuration loader using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM API Keys
    gemini_api_key: str = "stub"
    anthropic_api_key: str = "stub"

    # Web Search
    web_search_api_key: str = "stub"
    web_search_provider: str = "brave"

    # Google Drive
    google_drive_credentials_path: str = "./credentials.json"
    google_drive_folder_id: str = ""
    user_email: str = ""

    # Scheduling
    default_schedule: str = "0 6 * * *"

    # Logging
    log_level: str = "INFO"

    # Models
    llm_discovery_model: str = "gemini-3.1-pro-preview"
    llm_synthesis_model: str = "claude-sonnet-4-6"

    # Development
    use_stubs: bool = True

    # Paths
    data_dir: Path = Path("data")
    db_path: Path = Path("data/theaunties.db")
    context_dir: Path = Path("data/context")
    docs_dir: Path = Path("data/docs")


def get_settings(**overrides) -> Settings:
    """Create a Settings instance, optionally with overrides for testing."""
    return Settings(**overrides)
