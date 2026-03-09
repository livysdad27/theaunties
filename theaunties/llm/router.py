"""LLM routing abstraction — dispatches tasks to the appropriate model."""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Task types that determine which LLM to use."""
    DISCOVERY = "discovery"       # Source brainstorming, URL extraction → Gemini
    DATA_ANALYSIS = "data_analysis"  # Large-context raw data analysis → Gemini
    SYNTHESIS = "synthesis"       # Doc writing, research summary → Claude
    CHAT = "chat"                 # User conversation → Claude
    TOPIC_PARSING = "topic_parsing"  # Parse user intent → Claude


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    task_type: str = ""


@dataclass
class LLMCallLog:
    """Audit log entry for an LLM call."""
    timestamp: float
    task_type: str
    model: str
    prompt_preview: str  # First 200 chars of prompt
    response_preview: str  # First 200 chars of response
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMClient(Protocol):
    """Protocol for LLM client implementations."""
    @property
    def model_name(self) -> str: ...

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...


# Task type to model routing
_GEMINI_TASKS = {TaskType.DISCOVERY, TaskType.DATA_ANALYSIS}
_CLAUDE_TASKS = {TaskType.SYNTHESIS, TaskType.CHAT, TaskType.TOPIC_PARSING}


class LLMRouter:
    """Routes LLM tasks to the appropriate model client."""

    def __init__(self, gemini_client: LLMClient, claude_client: LLMClient):
        self._gemini = gemini_client
        self._claude = claude_client
        self._call_log: list[LLMCallLog] = []

    def _get_client(self, task_type: TaskType) -> LLMClient:
        if task_type in _GEMINI_TASKS:
            return self._gemini
        if task_type in _CLAUDE_TASKS:
            return self._claude
        raise ValueError(f"Unknown task type: {task_type}")

    async def complete(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Route a prompt to the appropriate model and return the response."""
        client = self._get_client(task_type)

        start = time.perf_counter()
        response = await client.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.task_type = task_type.value
        response.latency_ms = elapsed_ms

        log_entry = LLMCallLog(
            timestamp=time.time(),
            task_type=task_type.value,
            model=response.model,
            prompt_preview=prompt[:200],
            response_preview=response.text[:200],
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=elapsed_ms,
        )
        self._call_log.append(log_entry)
        logger.info(
            "LLM call: task=%s model=%s tokens=%d/%d latency=%.0fms",
            task_type.value,
            response.model,
            response.input_tokens,
            response.output_tokens,
            elapsed_ms,
        )

        return response

    @property
    def call_log(self) -> list[LLMCallLog]:
        return list(self._call_log)
