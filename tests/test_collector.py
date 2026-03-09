"""Tests for data collector module."""

import pytest
import httpx

from theaunties.agent.collector import CollectionResult, CollectionSummary, DataCollector


class TestCollectionResult:
    def test_success_result(self):
        r = CollectionResult(
            source_url="https://api.example.com",
            success=True,
            data='{"temp": 65}',
            data_format="json",
            status_code=200,
        )
        assert r.success
        assert r.data == '{"temp": 65}'
        assert r.collected_at is not None

    def test_failure_result(self):
        r = CollectionResult(
            source_url="https://api.example.com",
            success=False,
            error="Request timed out",
        )
        assert not r.success
        assert r.error == "Request timed out"


class TestCollectionSummary:
    def test_success_rate(self):
        summary = CollectionSummary(total=4, succeeded=3, failed=1)
        assert summary.success_rate == 0.75

    def test_success_rate_zero_total(self):
        summary = CollectionSummary(total=0, succeeded=0, failed=0)
        assert summary.success_rate == 0.0


class TestDataCollector:
    @pytest.mark.asyncio
    async def test_rejects_unsafe_url(self):
        """Collector should reject unsafe URLs without making a request."""
        collector = DataCollector()
        result = await collector.collect_one("http://localhost/secret")
        assert not result.success
        assert "safety check" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rejects_private_ip(self):
        """Collector should reject private IPs."""
        collector = DataCollector()
        result = await collector.collect_one("https://192.168.1.1/api")
        assert not result.success
        assert "safety check" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Collector should handle timeouts gracefully."""
        # Use a transport that always times out
        transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("timeout")))
        client = httpx.AsyncClient(transport=transport)
        collector = DataCollector(http_client=client)

        result = await collector.collect_one("https://api.example.com/slow")
        assert not result.success
        assert "timed out" in result.error.lower()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        """Collector should handle HTTP 4xx/5xx gracefully."""
        transport = httpx.MockTransport(lambda r: httpx.Response(404, text="Not Found"))
        client = httpx.AsyncClient(transport=transport)
        collector = DataCollector(http_client=client)

        result = await collector.collect_one("https://api.example.com/missing")
        assert not result.success
        assert "404" in result.error
        await client.aclose()

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Collector should handle connection errors gracefully."""
        transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
        client = httpx.AsyncClient(transport=transport)
        collector = DataCollector(http_client=client)

        result = await collector.collect_one("https://api.example.com/down")
        assert not result.success
        assert "error" in result.error.lower()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_successful_collection(self):
        """Collector should return data on success."""
        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json={"temperature": 65, "unit": "F"})
        )
        client = httpx.AsyncClient(transport=transport)
        collector = DataCollector(http_client=client)

        result = await collector.collect_one("https://api.example.com/weather", data_format="json")
        assert result.success
        assert result.status_code == 200
        assert "temperature" in result.data
        assert result.response_time_ms >= 0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_collect_from_multiple_sources(self):
        """Should collect from all sources and summarize results."""
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            if "fail" in str(request.url):
                return httpx.Response(500, text="Error")
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        collector = DataCollector(http_client=client)

        sources = [
            {"url": "https://api.example.com/good1", "data_format": "json"},
            {"url": "https://api.example.com/fail", "data_format": "json"},
            {"url": "https://api.example.com/good2", "data_format": "json"},
        ]

        summary = await collector.collect_from_sources(sources)
        assert summary.total == 3
        assert summary.succeeded == 2
        assert summary.failed == 1
        assert len(summary.results) == 3
        await client.aclose()
