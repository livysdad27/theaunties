"""Database connection and session management."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from theaunties.db.models import Base


def get_engine(db_path: Path | str = "data/theaunties.db"):
    """Create a SQLAlchemy engine for the given database path."""
    if str(db_path) == ":memory:":
        url = "sqlite:///:memory:"
    else:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    return create_engine(url, echo=False)


def get_session_factory(engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine)


def init_db(engine) -> None:
    """Create all tables in the database."""
    Base.metadata.create_all(engine)
