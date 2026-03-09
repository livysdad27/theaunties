"""Tests for database models and operations."""

from datetime import datetime, timezone

from sqlalchemy import inspect

from theaunties.db.database import get_engine, init_db
from theaunties.db.models import Base, ChatMessage, ContextLog, Run, Source, Topic


class TestDatabaseInit:
    def test_init_creates_all_tables(self, db_engine):
        """init_db should create all expected tables."""
        inspector = inspect(db_engine)
        table_names = inspector.get_table_names()
        assert "topics" in table_names
        assert "sources" in table_names
        assert "runs" in table_names
        assert "context_log" in table_names
        assert "chat_history" in table_names

    def test_in_memory_engine(self):
        """Should support in-memory SQLite for testing."""
        engine = get_engine(":memory:")
        init_db(engine)
        inspector = inspect(engine)
        assert "topics" in inspector.get_table_names()
        engine.dispose()


class TestTopicCRUD:
    def test_create_topic(self, db_session):
        """Should create a topic with required fields."""
        topic = Topic(
            name="Lake Travis Fishing",
            description="Monitor fishing conditions at Lake Travis",
            user_intent="I'm going fishing at Lake Travis this weekend",
            schedule="0 6 * * *",
        )
        db_session.add(topic)
        db_session.commit()

        assert topic.id is not None
        assert topic.status == "active"
        assert topic.created_at is not None

    def test_read_topic(self, db_session):
        """Should retrieve a saved topic."""
        topic = Topic(
            name="FDA Tracking",
            description="Track FDA regulatory changes",
            user_intent="Track any FDA regulatory changes affecting digital health startups",
        )
        db_session.add(topic)
        db_session.commit()

        loaded = db_session.get(Topic, topic.id)
        assert loaded.name == "FDA Tracking"
        assert loaded.user_intent == "Track any FDA regulatory changes affecting digital health startups"

    def test_default_schedule(self, db_session):
        """Topic should have default schedule if not specified."""
        topic = Topic(
            name="Test",
            description="Test topic",
            user_intent="Test",
        )
        db_session.add(topic)
        db_session.commit()
        assert topic.schedule == "0 6 * * *"


class TestSourceCRUD:
    def test_create_source_for_topic(self, db_session):
        """Should create a source linked to a topic."""
        topic = Topic(name="Weather", description="Weather data", user_intent="Weather check")
        db_session.add(topic)
        db_session.commit()

        source = Source(
            topic_id=topic.id,
            url="https://api.weather.gov/points/30.3,-97.8",
            source_type="REST API",
            data_format="json",
            description="NWS weather forecast for Lake Travis area",
        )
        db_session.add(source)
        db_session.commit()

        assert source.id is not None
        assert source.topic_id == topic.id
        assert source.status == "active"

    def test_topic_sources_relationship(self, db_session):
        """Topic.sources should return associated sources."""
        topic = Topic(name="Weather", description="Weather data", user_intent="Weather check")
        db_session.add(topic)
        db_session.commit()

        source = Source(
            topic_id=topic.id,
            url="https://api.example.com/data",
            source_type="REST API",
            data_format="json",
            description="Test source",
        )
        db_session.add(source)
        db_session.commit()

        db_session.refresh(topic)
        assert len(topic.sources) == 1
        assert topic.sources[0].url == "https://api.example.com/data"


class TestRunCRUD:
    def test_create_run(self, db_session):
        """Should create a run record for a topic."""
        topic = Topic(name="Test", description="Test", user_intent="Test")
        db_session.add(topic)
        db_session.commit()

        run = Run(topic_id=topic.id, sources_queried=3, sources_failed=1)
        db_session.add(run)
        db_session.commit()

        assert run.id is not None
        assert run.status == "running"
        assert run.started_at is not None
        assert run.sources_queried == 3

    def test_complete_run(self, db_session):
        """Should update run status on completion."""
        topic = Topic(name="Test", description="Test", user_intent="Test")
        db_session.add(topic)
        db_session.commit()

        run = Run(topic_id=topic.id)
        db_session.add(run)
        db_session.commit()

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.doc_url = "https://docs.google.com/document/d/abc123"
        db_session.commit()

        loaded = db_session.get(Run, run.id)
        assert loaded.status == "completed"
        assert loaded.doc_url is not None


class TestContextLogCRUD:
    def test_create_context_log(self, db_session):
        """Should log context changes with timestamps."""
        topic = Topic(name="Test", description="Test", user_intent="Test")
        db_session.add(topic)
        db_session.commit()

        log = ContextLog(
            topic_id=topic.id,
            change_type="created",
            change_detail="Initial context created from user intent",
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.timestamp is not None
        assert log.change_type == "created"


class TestChatMessageCRUD:
    def test_create_chat_message(self, db_session):
        """Should store chat messages."""
        topic = Topic(name="Test", description="Test", user_intent="Test")
        db_session.add(topic)
        db_session.commit()

        msg = ChatMessage(
            topic_id=topic.id,
            role="user",
            message="Track fishing conditions at Lake Travis",
        )
        db_session.add(msg)
        db_session.commit()

        assert msg.id is not None
        assert msg.timestamp is not None

    def test_chat_without_topic(self, db_session):
        """Should allow chat messages not linked to a topic."""
        msg = ChatMessage(
            topic_id=None,
            role="user",
            message="What can you help me with?",
        )
        db_session.add(msg)
        db_session.commit()

        assert msg.id is not None
        assert msg.topic_id is None
