"""Tests for the LLM routing layer."""

import pytest

from theaunties.llm.claude import ClaudeStubClient
from theaunties.llm.gemini import GeminiStubClient
from theaunties.llm.router import LLMResponse, LLMRouter, TaskType


@pytest.fixture
def gemini_stub():
    return GeminiStubClient()


@pytest.fixture
def claude_stub():
    return ClaudeStubClient()


@pytest.fixture
def router(gemini_stub, claude_stub):
    return LLMRouter(gemini_client=gemini_stub, claude_client=claude_stub)


class TestLLMResponse:
    def test_response_fields(self):
        """LLMResponse should have all expected fields."""
        r = LLMResponse(text="hello", model="test-model", input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert r.model == "test-model"
        assert r.input_tokens == 10
        assert r.output_tokens == 5
        assert r.latency_ms == 0.0
        assert r.task_type == ""


class TestRouting:
    @pytest.mark.asyncio
    async def test_discovery_routes_to_gemini(self, router, gemini_stub):
        """Discovery tasks should route to Gemini."""
        response = await router.complete(
            prompt="Discover data sources for weather tracking",
            task_type=TaskType.DISCOVERY,
        )
        assert response.model == gemini_stub.model_name

    @pytest.mark.asyncio
    async def test_data_analysis_routes_to_gemini(self, router, gemini_stub):
        """Data analysis tasks should route to Gemini."""
        response = await router.complete(
            prompt="Analyze the changes in this data",
            task_type=TaskType.DATA_ANALYSIS,
        )
        assert response.model == gemini_stub.model_name

    @pytest.mark.asyncio
    async def test_synthesis_routes_to_claude(self, router, claude_stub):
        """Synthesis tasks should route to Claude."""
        response = await router.complete(
            prompt="Synthesize a summary document from this data",
            task_type=TaskType.SYNTHESIS,
        )
        assert response.model == claude_stub.model_name

    @pytest.mark.asyncio
    async def test_chat_routes_to_claude(self, router, claude_stub):
        """Chat tasks should route to Claude."""
        response = await router.complete(
            prompt="The user has a chat question about their topic",
            task_type=TaskType.CHAT,
        )
        assert response.model == claude_stub.model_name

    @pytest.mark.asyncio
    async def test_topic_parsing_routes_to_claude(self, router, claude_stub):
        """Topic parsing tasks should route to Claude."""
        response = await router.complete(
            prompt="Parse the user's topic intent from this message",
            task_type=TaskType.TOPIC_PARSING,
        )
        assert response.model == claude_stub.model_name


class TestCallLogging:
    @pytest.mark.asyncio
    async def test_calls_are_logged(self, router):
        """Each LLM call should be logged."""
        assert len(router.call_log) == 0

        await router.complete(prompt="test prompt", task_type=TaskType.DISCOVERY)
        assert len(router.call_log) == 1

        log = router.call_log[0]
        assert log.task_type == "discovery"
        assert log.prompt_preview == "test prompt"
        assert log.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_log_tracks_model(self, router):
        """Log should record which model was used."""
        await router.complete(prompt="test", task_type=TaskType.DISCOVERY)
        await router.complete(prompt="test", task_type=TaskType.SYNTHESIS)

        assert len(router.call_log) == 2
        assert router.call_log[0].model == "gemini-3.1-pro-preview"
        assert router.call_log[1].model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_log_truncates_long_prompts(self, router):
        """Log should truncate long prompts to 200 chars."""
        long_prompt = "x" * 500
        await router.complete(prompt=long_prompt, task_type=TaskType.DISCOVERY)

        log = router.call_log[0]
        assert len(log.prompt_preview) == 200


class TestStubResponses:
    @pytest.mark.asyncio
    async def test_gemini_discovery_response(self, gemini_stub):
        """Gemini stub should return source-related response for discovery prompts."""
        response = await gemini_stub.complete(prompt="Discover sources for this topic")
        assert "api.weather.gov" in response.text
        assert response.input_tokens > 0
        assert response.output_tokens > 0

    @pytest.mark.asyncio
    async def test_claude_synthesis_response(self, claude_stub):
        """Claude stub should return structured doc for synthesis prompts."""
        response = await claude_stub.complete(prompt="Synthesize a summary document")
        assert "## Summary" in response.text

    @pytest.mark.asyncio
    async def test_claude_topic_parsing_response(self, claude_stub):
        """Claude stub should return JSON for topic parsing prompts."""
        response = await claude_stub.complete(prompt="Parse the topic intent from this")
        assert "name" in response.text

    @pytest.mark.asyncio
    async def test_response_includes_task_type_after_routing(self, router):
        """Response should have task_type set after routing."""
        response = await router.complete(prompt="test", task_type=TaskType.CHAT)
        assert response.task_type == "chat"
