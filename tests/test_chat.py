"""Tests for the chat handler."""

from pathlib import Path

import pytest

from theaunties.agent.context import ContextManager
from theaunties.chat.handler import ChatHandler, ChatResponse, ChatState
from theaunties.db.models import ChatMessage, Topic
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
def context_mgr(tmp_path: Path):
    return ContextManager(context_dir=tmp_path / "context")


@pytest.fixture
def handler(llm_router, context_mgr, db_session):
    return ChatHandler(
        llm_router=llm_router,
        context_manager=context_mgr,
        db_session=db_session,
    )


class TestTopicCreationFlow:
    @pytest.mark.asyncio
    async def test_new_message_parses_topic(self, handler):
        """First message should parse into a topic and ask for confirmation."""
        response = await handler.handle_message(
            "I'm going fishing at Lake Travis this weekend — keep me updated on conditions"
        )
        assert handler.state == ChatState.AWAITING_CONFIRMATION
        assert response.action == "parsed"

    @pytest.mark.asyncio
    async def test_confirm_creates_topic(self, handler, db_session):
        """Confirming should create the topic in the database."""
        await handler.handle_message("Track fishing conditions at Lake Travis")
        response = await handler.handle_message("yes")

        assert response.action == "created"
        assert response.topic_id is not None
        assert handler.state == ChatState.ACTIVE

        # Verify topic in DB
        topic = db_session.get(Topic, response.topic_id)
        assert topic is not None

    @pytest.mark.asyncio
    async def test_cancel_returns_to_idle(self, handler):
        """Cancelling should return to idle state."""
        await handler.handle_message("Track something")
        response = await handler.handle_message("no")

        assert response.action == "cancelled"
        assert handler.state == ChatState.IDLE

    @pytest.mark.asyncio
    async def test_confirm_variations(self, handler):
        """Various confirmation phrases should work."""
        for confirm in ["yes", "y", "looks good", "confirm", "go", "lgtm", "ok", "sure"]:
            h = ChatHandler(
                llm_router=handler._llm,
                context_manager=handler._context,
                db_session=handler._db,
            )
            await h.handle_message("Track weather")
            response = await h.handle_message(confirm)
            assert response.action == "created", f"Failed for: {confirm}"


class TestActiveChatFlow:
    @pytest.mark.asyncio
    async def test_refinement_after_creation(self, handler):
        """Should handle refinement messages after topic is created."""
        await handler.handle_message("Track weather at Lake Travis")
        await handler.handle_message("yes")

        response = await handler.handle_message("Focus more on water temperature")
        assert handler.state == ChatState.ACTIVE
        assert response.topic_id is not None

    @pytest.mark.asyncio
    async def test_qa_about_topic(self, handler):
        """Should answer questions about the active topic."""
        await handler.handle_message("Track weather data")
        await handler.handle_message("yes")

        response = await handler.handle_message("What sources are you using?")
        assert response.topic_id is not None
        assert response.message != ""


class TestChatHistory:
    @pytest.mark.asyncio
    async def test_messages_stored_in_db(self, handler, db_session):
        """All messages should be stored in chat_history."""
        await handler.handle_message("Track fishing conditions")

        messages = db_session.query(ChatMessage).all()
        # At least user message + assistant response
        assert len(messages) >= 2
        roles = {m.role for m in messages}
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_messages_linked_to_topic_after_creation(self, handler, db_session):
        """Messages after topic creation should be linked to the topic."""
        await handler.handle_message("Track weather")
        response = await handler.handle_message("yes")
        topic_id = response.topic_id

        await handler.handle_message("What's the forecast?")

        # The last message should be linked to the topic
        last_msg = (
            db_session.query(ChatMessage)
            .filter(ChatMessage.topic_id == topic_id)
            .order_by(ChatMessage.timestamp.desc())
            .first()
        )
        assert last_msg is not None


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_message_after_topic(self, handler):
        """Handler should handle edge cases gracefully."""
        await handler.handle_message("Track weather")
        await handler.handle_message("yes")
        # Short/unclear refinement
        response = await handler.handle_message("hmm")
        assert response.message != ""
