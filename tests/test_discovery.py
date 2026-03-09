"""Tests for source discovery module."""

import pytest

from theaunties.agent.discovery import (
    CandidateSource,
    RejectedSource,
    SourceDiscovery,
    ValidatedSource,
    WebSearchStub,
    is_safe_url,
)
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
def discovery(llm_router):
    return SourceDiscovery(llm_router=llm_router)


class TestURLSafety:
    def test_accepts_valid_https(self):
        safe, reason = is_safe_url("https://api.weather.gov/data")
        assert safe is True

    def test_rejects_http(self):
        safe, reason = is_safe_url("http://api.weather.gov/data")
        assert safe is False
        assert "HTTPS" in reason

    def test_rejects_localhost(self):
        safe, reason = is_safe_url("https://localhost/data")
        assert safe is False

    def test_rejects_127_0_0_1(self):
        safe, reason = is_safe_url("https://127.0.0.1/data")
        assert safe is False

    def test_rejects_private_ip_192(self):
        safe, reason = is_safe_url("https://192.168.1.1/data")
        assert safe is False
        assert "Private" in reason

    def test_rejects_private_ip_10(self):
        safe, reason = is_safe_url("https://10.0.0.1/data")
        assert safe is False

    def test_rejects_private_ip_172(self):
        safe, reason = is_safe_url("https://172.16.0.1/data")
        assert safe is False

    def test_rejects_malformed_url(self):
        safe, reason = is_safe_url("not a url at all")
        assert safe is False

    def test_rejects_no_scheme(self):
        safe, reason = is_safe_url("api.weather.gov/data")
        assert safe is False

    def test_rejects_ftp(self):
        safe, reason = is_safe_url("ftp://files.example.com/data")
        assert safe is False

    def test_rejects_internal_hostname(self):
        safe, reason = is_safe_url("https://myserver.local/api")
        assert safe is False

    def test_rejects_internal_domain(self):
        safe, reason = is_safe_url("https://db.internal/api")
        assert safe is False

    def test_accepts_real_api_urls(self):
        urls = [
            "https://api.weather.gov/points/30.3,-97.8",
            "https://waterservices.usgs.gov/nwis/iv/",
            "https://api.open-meteo.com/v1/forecast",
        ]
        for url in urls:
            safe, _ = is_safe_url(url)
            assert safe is True, f"Expected {url} to be safe"


class TestWebSearchStub:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        stub = WebSearchStub()
        results = await stub.search("weather API")
        assert len(results) > 0
        assert all("url" in r for r in results)


class TestSourceDiscovery:
    @pytest.mark.asyncio
    async def test_brainstorm_returns_candidates(self, discovery):
        """Brainstorming should return a list of candidate sources."""
        candidates = await discovery.brainstorm_sources(
            "Lake Travis Fishing",
            "Monitor fishing conditions at Lake Travis",
        )
        assert len(candidates) > 0
        assert all(isinstance(c, CandidateSource) for c in candidates)

    @pytest.mark.asyncio
    async def test_candidates_have_urls(self, discovery):
        """Each candidate should have a URL."""
        candidates = await discovery.brainstorm_sources(
            "Weather", "Discover data sources for weather tracking"
        )
        assert all(c.url for c in candidates)

    @pytest.mark.asyncio
    async def test_search_returns_results(self, discovery):
        """Web search should return results."""
        results = await discovery.search_for_sources(
            "Weather", "Weather tracking"
        )
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_parse_candidates_from_json(self, discovery):
        """Should parse JSON array of sources from LLM output."""
        json_text = '''[
            {"url": "https://api.example.com/data", "source_type": "REST API", "data_format": "json", "description": "Test API"}
        ]'''
        candidates = discovery._parse_candidates(json_text)
        assert len(candidates) == 1
        assert candidates[0].url == "https://api.example.com/data"

    @pytest.mark.asyncio
    async def test_parse_candidates_fallback_url_extraction(self, discovery):
        """Should extract URLs from plain text if JSON parsing fails."""
        text = "Check out https://api.example.com/weather for weather data"
        candidates = discovery._parse_candidates(text)
        assert len(candidates) >= 1
        assert "api.example.com" in candidates[0].url
