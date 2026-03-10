"""Tests for the BraveSearchClient (mocked — no real API calls)."""

import json

import httpx
import pytest

from theaunties.agent.discovery import BraveSearchClient


def _make_brave_response(results: list[dict]) -> dict:
    """Build a Brave Search API response structure."""
    return {
        "query": {"original": "test query"},
        "web": {
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                    "age": "2d",
                }
                for r in results
            ]
        },
    }


class TestBraveSearchClient:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        """Should return parsed search results."""
        mock_data = _make_brave_response([
            {"title": "NWS API", "url": "https://api.weather.gov", "description": "Weather data"},
            {"title": "USGS", "url": "https://waterservices.usgs.gov", "description": "Water data"},
        ])

        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=mock_data)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="test-key", http_client=client)
            results = await brave.search("weather API")

        assert len(results) == 2
        assert results[0]["title"] == "NWS API"
        assert results[0]["url"] == "https://api.weather.gov"
        assert results[1]["title"] == "USGS"

    @pytest.mark.asyncio
    async def test_results_have_expected_keys(self):
        """Each result should have title, url, and description."""
        mock_data = _make_brave_response([
            {"title": "Test", "url": "https://example.com", "description": "A test"},
        ])

        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=mock_data)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="test-key", http_client=client)
            results = await brave.search("test")

        assert len(results) == 1
        assert "title" in results[0]
        assert "url" in results[0]
        assert "description" in results[0]

    @pytest.mark.asyncio
    async def test_sends_api_key_header(self):
        """Should send the API key in X-Subscription-Token header."""
        captured_request = None

        def handler(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=_make_brave_response([]))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="my-secret-key", http_client=client)
            await brave.search("test")

        assert captured_request is not None
        assert captured_request.headers["X-Subscription-Token"] == "my-secret-key"

    @pytest.mark.asyncio
    async def test_sends_query_param(self):
        """Should send the query as the 'q' parameter."""
        captured_request = None

        def handler(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=_make_brave_response([]))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="key", http_client=client)
            await brave.search("lake travis fishing conditions")

        assert captured_request is not None
        assert "lake+travis+fishing+conditions" in str(captured_request.url) or \
               "lake%20travis%20fishing%20conditions" in str(captured_request.url)

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        """Should return empty list on HTTP error, not crash."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "Unauthorized"})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="bad-key", http_client=client)
            results = await brave.search("test")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_network_error(self):
        """Should return empty list on network failure, not crash."""
        def handler(request):
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="key", http_client=client)
            results = await brave.search("test")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        """Should handle a response with no web results."""
        mock_data = {"query": {"original": "test"}, "web": {"results": []}}

        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=mock_data)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="key", http_client=client)
            results = await brave.search("obscure query")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_missing_web_key(self):
        """Should handle response missing the 'web' key entirely."""
        mock_data = {"query": {"original": "test"}}

        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=mock_data)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="key", http_client=client)
            results = await brave.search("test")

        assert results == []

    @pytest.mark.asyncio
    async def test_count_parameter(self):
        """Should pass count parameter to the API."""
        captured_request = None

        def handler(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=_make_brave_response([]))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            brave = BraveSearchClient(api_key="key", http_client=client)
            await brave.search("test", count=5)

        assert captured_request is not None
        assert "count=5" in str(captured_request.url)
