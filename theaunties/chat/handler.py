"""Chat handler — routes user messages, manages topic lifecycle."""

import json
import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from theaunties.agent.context import ContextManager
from theaunties.db.models import ChatMessage, Source, Topic
from theaunties.llm.router import LLMRouter, TaskType
from theaunties.prompts.chat import (
    qa_prompt,
    refinement_prompt,
    topic_confirmation_prompt,
    topic_parsing_prompt,
)

logger = logging.getLogger(__name__)


class ChatState(str, Enum):
    """Conversation states for topic setup flow."""
    IDLE = "idle"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ACTIVE = "active"


@dataclass
class ParsedTopic:
    """A topic parsed from user input."""
    name: str
    description: str
    key_aspects: list[str]
    suggested_schedule: str = "0 6 * * *"
    clarifying_questions: list[str] | None = None
    needs_clarification: bool = False


@dataclass
class ChatResponse:
    """Response from the chat handler."""
    message: str
    topic_id: int | None = None
    state: ChatState = ChatState.IDLE
    action: str = ""  # created, confirmed, refined, answered


class ChatHandler:
    """Handles user chat messages and manages topic lifecycle."""

    def __init__(
        self,
        llm_router: LLMRouter,
        context_manager: ContextManager,
        db_session: Session,
    ):
        self._llm = llm_router
        self._context = context_manager
        self._db = db_session
        self._pending_topic: ParsedTopic | None = None
        self._state = ChatState.IDLE
        self._active_topic_id: int | None = None

    @property
    def state(self) -> ChatState:
        return self._state

    @property
    def active_topic_id(self) -> int | None:
        return self._active_topic_id

    async def handle_message(self, message: str) -> ChatResponse:
        """Route a user message and return a response."""
        # Store user message
        self._store_message("user", message)

        if self._state == ChatState.AWAITING_CONFIRMATION:
            response = await self._handle_confirmation(message)
        elif self._state == ChatState.ACTIVE and self._active_topic_id:
            response = await self._handle_active_chat(message)
        else:
            response = await self._handle_new_message(message)

        # Store assistant response
        self._store_message("assistant", response.message, topic_id=response.topic_id)
        return response

    async def _handle_new_message(self, message: str) -> ChatResponse:
        """Handle a message when no topic is being set up."""
        # Try to parse as a new topic
        parsed = await self._parse_topic(message)

        if parsed.needs_clarification and parsed.clarifying_questions:
            questions = "\n".join(f"- {q}" for q in parsed.clarifying_questions)
            return ChatResponse(
                message=f"I'd like to help track that. A few questions first:\n{questions}",
                state=ChatState.IDLE,
                action="clarifying",
            )

        # Topic parsed successfully — ask for confirmation
        self._pending_topic = parsed
        self._state = ChatState.AWAITING_CONFIRMATION

        confirmation = await self._generate_confirmation(parsed)
        return ChatResponse(
            message=confirmation,
            state=ChatState.AWAITING_CONFIRMATION,
            action="parsed",
        )

    async def _handle_confirmation(self, message: str) -> ChatResponse:
        """Handle a response during topic confirmation."""
        lower = message.lower().strip()

        if lower in ("yes", "y", "looks good", "confirm", "go", "lgtm", "ok", "sure"):
            # Create the topic
            if self._pending_topic is None:
                self._state = ChatState.IDLE
                return ChatResponse(
                    message="Something went wrong. Please describe your topic again.",
                    state=ChatState.IDLE,
                )

            topic = self._create_topic(self._pending_topic)
            self._active_topic_id = topic.id
            self._state = ChatState.ACTIVE
            self._pending_topic = None

            return ChatResponse(
                message=(
                    f"Topic '{topic.name}' is set up and ready. "
                    f"I'll start discovering data sources and begin monitoring. "
                    f"You can refine what I'm tracking anytime."
                ),
                topic_id=topic.id,
                state=ChatState.ACTIVE,
                action="created",
            )

        elif lower in ("no", "n", "cancel", "start over"):
            self._state = ChatState.IDLE
            self._pending_topic = None
            return ChatResponse(
                message="No problem. Tell me what you'd like to track and I'll start fresh.",
                state=ChatState.IDLE,
                action="cancelled",
            )

        else:
            # Treat as a refinement of the pending topic
            return ChatResponse(
                message="Got it, I'll adjust. Does the updated plan look right? (yes/no)",
                state=ChatState.AWAITING_CONFIRMATION,
                action="refining",
            )

    async def _handle_active_chat(self, message: str) -> ChatResponse:
        """Handle messages when a topic is active (refinement/Q&A)."""
        topic = self._db.get(Topic, self._active_topic_id)
        if topic is None:
            self._state = ChatState.IDLE
            self._active_topic_id = None
            return ChatResponse(
                message="Topic not found. Let's set up a new one.",
                state=ChatState.IDLE,
            )

        context = self._context.load_context(topic.id)
        context_text = context.to_prompt_context() if context else ""

        # Get chat history
        history = self._get_recent_history(topic.id, limit=10)

        # Use LLM to determine intent (refinement vs Q&A)
        prompt = refinement_prompt(
            user_message=message,
            topic_name=topic.name,
            topic_description=topic.description,
            current_context=context_text,
            chat_history=history,
        )

        response = await self._llm.complete(
            prompt=prompt,
            task_type=TaskType.CHAT,
        )

        # Try to parse the response
        try:
            data = json.loads(response.text)
            action = data.get("action", "general_response")
            reply = data.get("response", response.text)

            # Apply refinements if any
            if action == "refine_topic" and context:
                changes = data.get("changes", {})
                if changes.get("add_aspects"):
                    self._context.add_clarification(
                        topic.id,
                        f"User wants to track: {', '.join(changes['add_aspects'])}",
                    )

            return ChatResponse(
                message=reply,
                topic_id=topic.id,
                state=ChatState.ACTIVE,
                action=action,
            )
        except (json.JSONDecodeError, TypeError):
            return ChatResponse(
                message=response.text,
                topic_id=topic.id,
                state=ChatState.ACTIVE,
                action="general_response",
            )

    async def _parse_topic(self, message: str) -> ParsedTopic:
        """Use LLM to parse a user message into a topic."""
        prompt = topic_parsing_prompt(message)
        response = await self._llm.complete(
            prompt=prompt,
            task_type=TaskType.TOPIC_PARSING,
        )

        try:
            data = json.loads(response.text)
            return ParsedTopic(
                name=data.get("name", "Untitled Topic"),
                description=data.get("description", message),
                key_aspects=data.get("key_aspects", []),
                suggested_schedule=data.get("suggested_schedule", "0 6 * * *"),
                clarifying_questions=data.get("clarifying_questions"),
                needs_clarification=data.get("needs_clarification", False),
            )
        except (json.JSONDecodeError, TypeError):
            # Fallback: use the message directly
            return ParsedTopic(
                name=message[:50],
                description=message,
                key_aspects=[],
            )

    async def _generate_confirmation(self, parsed: ParsedTopic) -> str:
        """Generate a confirmation message for the user."""
        prompt = topic_confirmation_prompt(
            parsed.name, parsed.description, parsed.key_aspects
        )
        response = await self._llm.complete(
            prompt=prompt,
            task_type=TaskType.CHAT,
        )
        return response.text

    def _create_topic(self, parsed: ParsedTopic) -> Topic:
        """Save a parsed topic to the database."""
        topic = Topic(
            name=parsed.name,
            description=parsed.description,
            user_intent=parsed.description,
            schedule=parsed.suggested_schedule,
        )
        self._db.add(topic)
        self._db.commit()

        # Create initial context
        self._context.create_context(
            topic_id=topic.id,
            topic_name=parsed.name,
            original_intent=parsed.description,
            description=parsed.description,
            key_aspects=parsed.key_aspects,
        )

        return topic

    def _store_message(self, role: str, message: str, topic_id: int | None = None) -> None:
        """Store a chat message in the database."""
        tid = topic_id or self._active_topic_id
        msg = ChatMessage(topic_id=tid, role=role, message=message)
        self._db.add(msg)
        self._db.commit()

    def _get_recent_history(self, topic_id: int, limit: int = 10) -> list[dict]:
        """Get recent chat history for a topic."""
        messages = (
            self._db.query(ChatMessage)
            .filter(ChatMessage.topic_id == topic_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": m.role, "message": m.message}
            for m in reversed(messages)
        ]
