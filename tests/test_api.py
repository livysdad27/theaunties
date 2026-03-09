"""Tests for the FastAPI endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from theaunties.main import app, _state, _build_components
from theaunties.config import Settings
from theaunties.db.models import Topic


class MockScheduler:
    """Mock scheduler that doesn't need an event loop."""

    def __init__(self):
        self._topics: dict[int, str] = {}

    def start(self): pass
    def shutdown(self): pass

    def add_topic(self, topic_id: int, cron_expression: str) -> str:
        self._topics[topic_id] = cron_expression
        return f"mock_job_{topic_id}"

    def remove_topic(self, topic_id: int):
        self._topics.pop(topic_id, None)

    def get_next_run(self, topic_id: int):
        return None

    def get_scheduled_topics(self):
        return [{"topic_id": tid, "job_id": f"mock_{tid}", "next_run": None}
                for tid in self._topics]


@pytest.fixture
def test_app(tmp_path):
    """Create a test FastAPI app with in-memory DB and mock scheduler."""
    settings = Settings(
        gemini_api_key="test",
        anthropic_api_key="test",
        web_search_api_key="test",
        use_stubs=True,
        data_dir=tmp_path,
        db_path=tmp_path / "test.db",
        context_dir=tmp_path / "context",
        docs_dir=tmp_path / "docs",
    )

    components = _build_components(settings)
    _state["components"] = components
    _state["scheduler"] = MockScheduler()

    # Create chat handler
    from theaunties.chat.handler import ChatHandler
    from theaunties.agent.context import ContextManager

    session = components["session_factory"]()
    context_mgr = ContextManager(context_dir=settings.context_dir)
    handler = ChatHandler(
        llm_router=components["llm_router"],
        context_manager=context_mgr,
        db_session=session,
    )
    _state["chat_handler"] = handler
    _state["chat_session"] = session

    client = TestClient(app, raise_server_exceptions=True)
    yield client

    session.close()


class TestChatEndpoint:
    def test_post_chat(self, test_app):
        """POST /chat should return a response."""
        response = test_app.post("/chat", json={"message": "Track weather at Lake Travis"})
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "state" in data

    def test_chat_topic_creation_flow(self, test_app):
        """Should create a topic through chat."""
        # First message — parse topic
        r1 = test_app.post("/chat", json={"message": "Track fishing conditions at Lake Travis"})
        assert r1.status_code == 200
        assert r1.json()["state"] == "awaiting_confirmation"

        # Confirm
        r2 = test_app.post("/chat", json={"message": "yes"})
        assert r2.status_code == 200
        assert r2.json()["action"] == "created"
        assert r2.json()["topic_id"] is not None


class TestTopicsEndpoint:
    def test_list_empty_topics(self, test_app):
        """GET /topics should return empty list initially."""
        response = test_app.get("/topics")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_after_creation(self, test_app):
        """GET /topics should return created topics."""
        test_app.post("/chat", json={"message": "Track weather"})
        test_app.post("/chat", json={"message": "yes"})

        response = test_app.get("/topics")
        assert response.status_code == 200
        topics = response.json()
        assert len(topics) >= 1


class TestTopicStatusEndpoint:
    def test_status_not_found(self, test_app):
        """GET /topics/999/status should return 404."""
        response = test_app.get("/topics/999/status")
        assert response.status_code == 404

    def test_status_after_creation(self, test_app):
        """GET /topics/{id}/status should return topic info."""
        test_app.post("/chat", json={"message": "Track weather"})
        r = test_app.post("/chat", json={"message": "yes"})
        topic_id = r.json()["topic_id"]

        response = test_app.get(f"/topics/{topic_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == topic_id
        assert data["status"] == "active"
