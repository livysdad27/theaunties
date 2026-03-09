"""Data collector — fetches data from registered sources."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from theaunties.agent.discovery import is_safe_url

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result of collecting data from a single source."""
    source_url: str
    success: bool
    data: str = ""
    data_format: str = ""
    status_code: int = 0
    error: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: float = 0.0


@dataclass
class CollectionSummary:
    """Summary of a collection run across all sources."""
    results: list[CollectionResult] = field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    failed: int = 0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total if self.total > 0 else 0.0


class DataCollector:
    """Collects data from registered sources via HTTP GET."""

    def __init__(self, http_client: httpx.AsyncClient | None = None, timeout: float = 15.0):
        self._http = http_client
        self._timeout = timeout

    async def collect_from_sources(self, sources: list[dict]) -> CollectionSummary:
        """Collect data from a list of sources.

        Args:
            sources: List of dicts with at least 'url' and 'data_format' keys.

        Returns:
            CollectionSummary with results from all sources.
        """
        summary = CollectionSummary(total=len(sources))

        for source in sources:
            result = await self.collect_one(
                url=source["url"],
                data_format=source.get("data_format", "unknown"),
            )
            summary.results.append(result)
            if result.success:
                summary.succeeded += 1
            else:
                summary.failed += 1

        return summary

    async def collect_one(self, url: str, data_format: str = "unknown") -> CollectionResult:
        """Collect data from a single source.

        Performs safety validation, makes a GET request, and returns the result.
        """
        # Safety check
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            logger.warning("Unsafe URL rejected: %s (%s)", url, reason)
            return CollectionResult(
                source_url=url,
                success=False,
                error=f"URL safety check failed: {reason}",
            )

        client = self._http or httpx.AsyncClient(timeout=self._timeout)
        should_close = self._http is None

        try:
            import time
            start = time.perf_counter()
            response = await client.get(url, follow_redirects=True)
            elapsed = (time.perf_counter() - start) * 1000

            response.raise_for_status()

            return CollectionResult(
                source_url=url,
                success=True,
                data=response.text,
                data_format=data_format,
                status_code=response.status_code,
                response_time_ms=elapsed,
            )

        except httpx.TimeoutException:
            logger.warning("Timeout collecting from %s", url)
            return CollectionResult(
                source_url=url,
                success=False,
                error="Request timed out",
            )

        except httpx.HTTPStatusError as e:
            logger.warning("HTTP %d from %s", e.response.status_code, url)
            return CollectionResult(
                source_url=url,
                success=False,
                status_code=e.response.status_code,
                error=f"HTTP {e.response.status_code}",
            )

        except httpx.RequestError as e:
            logger.warning("Request error from %s: %s", url, e)
            return CollectionResult(
                source_url=url,
                success=False,
                error=f"Request error: {e}",
            )

        finally:
            if should_close:
                await client.aclose()
