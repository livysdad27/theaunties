"""Shared test fixtures for theAunties."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from theaunties.config import Settings
from theaunties.db.database import init_db
from theaunties.db.models import Base


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    """Create a database session for testing."""
    factory = sessionmaker(bind=db_engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure."""
    context_dir = tmp_path / "context"
    docs_dir = tmp_path / "docs"
    context_dir.mkdir()
    docs_dir.mkdir()
    return tmp_path


@pytest.fixture
def test_settings(tmp_data_dir: Path) -> Settings:
    """Create test settings with temporary paths and stubs enabled."""
    return Settings(
        gemini_api_key="test-gemini-key",
        anthropic_api_key="test-anthropic-key",
        web_search_api_key="test-search-key",
        use_stubs=True,
        data_dir=tmp_data_dir,
        db_path=tmp_data_dir / "test.db",
        context_dir=tmp_data_dir / "context",
        docs_dir=tmp_data_dir / "docs",
    )
