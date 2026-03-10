"""Claude LLM client — stub and real implementations.

To swap from stub to real:
1. Set USE_STUBS=false in .env
2. Set ANTHROPIC_API_KEY to your real API key
3. The real client uses the anthropic SDK
"""

from theaunties.llm.router import LLMResponse


class ClaudeStubClient:
    """Stub Claude client that returns canned responses for testing."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Return different canned responses based on prompt content
        if "topic" in prompt.lower() and ("parse" in prompt.lower() or "intent" in prompt.lower()):
            text = (
                '{"name": "Lake Travis Fishing Conditions", '
                '"description": "Monitor fishing conditions at Lake Travis including weather, water temperature, and water levels", '
                '"key_aspects": ["water temperature", "wind speed", "water level", "weather forecast"]}'
            )
        elif "synthesize" in prompt.lower() or "summary" in prompt.lower() or "document" in prompt.lower():
            text = (
                "## Summary\n"
                "Conditions at Lake Travis remain favorable for fishing. "
                "Water temperature has risen slightly to 65F, and wind speeds have decreased.\n\n"
                "## What Changed\n"
                "- Water temperature: 62F → 65F (Source: USGS Water Services)\n"
                "- Wind speed: 15mph → 8mph (Source: NWS API)\n\n"
                "## Detailed Findings\n"
                "Water temperature data from USGS Water Services shows a 3-degree increase "
                "over the past 24 hours [source: waterservices.usgs.gov].\n"
            )
        elif "chat" in prompt.lower() or "question" in prompt.lower():
            text = (
                "I'm tracking fishing conditions at Lake Travis for you. "
                "Currently monitoring water temperature, wind speed, and water levels "
                "from 3 data sources. Would you like me to adjust what I'm tracking?"
            )
        else:
            text = (
                "Based on the available data, here is my analysis:\n"
                "The monitored conditions show expected patterns with no significant anomalies.\n"
            )

        return LLMResponse(
            text=text,
            model=self._model,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
        )


class ClaudeClient:
    """Real Claude client using the anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._client.messages.create(**kwargs)

        text = response.content[0].text if response.content else ""
        return LLMResponse(
            text=text,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
