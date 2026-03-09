"""Gemini LLM client — stub and real implementations.

To swap from stub to real:
1. Set USE_STUBS=false in .env
2. Set GEMINI_API_KEY to your real API key
3. The real client uses google-genai SDK
"""

from theaunties.llm.router import LLMResponse


class GeminiStubClient:
    """Stub Gemini client that returns canned responses for testing."""

    def __init__(self, model: str = "gemini-3.1-pro-preview"):
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
        if "source" in prompt.lower() or "discover" in prompt.lower():
            text = (
                "Based on the topic, here are potential data sources:\n"
                "1. https://api.weather.gov - National Weather Service API (free, no auth)\n"
                "2. https://waterservices.usgs.gov/nwis - USGS Water Services (free, no auth)\n"
                "3. https://api.open-meteo.com/v1/forecast - Open-Meteo weather API (free, no auth)\n"
            )
        elif "analy" in prompt.lower() or "change" in prompt.lower():
            text = (
                "Analysis of collected data:\n"
                "- Water temperature increased from 62F to 65F (notable change)\n"
                "- Wind speed decreased from 15mph to 8mph (favorable)\n"
                "- No significant changes in water level\n"
            )
        else:
            text = (
                "Here is a summary of the gathered information:\n"
                "The data shows stable conditions with minor variations in the monitored parameters.\n"
            )

        return LLMResponse(
            text=text,
            model=self._model,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
        )


class GeminiClient:
    """Real Gemini client using google-genai SDK.

    Placeholder — activate by setting USE_STUBS=false.
    """

    def __init__(self, api_key: str, model: str = "gemini-3.1-pro-preview"):
        self._api_key = api_key
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
        raise NotImplementedError(
            "Real Gemini client not yet implemented. Set USE_STUBS=true in .env."
        )
