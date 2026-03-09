"""Source discovery — finds and validates public data sources for topics."""

import ipaddress
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from theaunties.llm.router import LLMRouter, TaskType
from theaunties.prompts.discovery import (
    source_brainstorm_prompt,
    source_validation_prompt,
    web_search_query_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class CandidateSource:
    """A candidate data source discovered during brainstorming."""
    url: str
    source_type: str
    data_format: str
    description: str
    auth_required: bool = False


@dataclass
class ValidatedSource:
    """A source that has been validated with a test request."""
    url: str
    source_type: str
    data_format: str
    description: str
    sample_data: str = ""


@dataclass
class RejectedSource:
    """A source that failed validation."""
    url: str
    reason: str


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate a URL for safety (SSRF protection).

    Returns (is_safe, reason) tuple.
    Rejects: non-HTTPS, private IPs, localhost, malformed URLs.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme != "https":
        return False, f"Only HTTPS allowed, got {parsed.scheme!r}"

    if not parsed.hostname:
        return False, "No hostname in URL"

    hostname = parsed.hostname.lower()

    # Reject localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Localhost URLs not allowed"

    # Try to parse as IP address and check for private ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private:
            return False, "Private IP addresses not allowed"
        if ip.is_loopback:
            return False, "Loopback addresses not allowed"
        if ip.is_link_local:
            return False, "Link-local addresses not allowed"
        if ip.is_reserved:
            return False, "Reserved addresses not allowed"
    except ValueError:
        # Not an IP address (it's a hostname) — that's fine
        pass

    # Reject common internal hostnames
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return False, "Internal hostnames not allowed"

    return True, "OK"


class WebSearchStub:
    """Stub web search client that returns canned results."""

    async def search(self, query: str) -> list[dict]:
        """Return canned search results for testing."""
        return [
            {
                "title": "National Weather Service API",
                "url": "https://api.weather.gov",
                "description": "Free weather data API from NWS",
            },
            {
                "title": "USGS Water Services",
                "url": "https://waterservices.usgs.gov/nwis/iv/",
                "description": "Real-time water data from USGS",
            },
            {
                "title": "Open-Meteo Weather API",
                "url": "https://api.open-meteo.com/v1/forecast",
                "description": "Free weather forecast API",
            },
        ]


class SourceDiscovery:
    """Discovers and validates public data sources for research topics."""

    def __init__(
        self,
        llm_router: LLMRouter,
        web_search: WebSearchStub | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._llm = llm_router
        self._search = web_search or WebSearchStub()
        self._http = http_client

    async def brainstorm_sources(
        self,
        topic_name: str,
        topic_description: str,
        existing_sources: list[str] | None = None,
    ) -> list[CandidateSource]:
        """Use the LLM to brainstorm candidate data sources for a topic."""
        prompt = source_brainstorm_prompt(topic_name, topic_description, existing_sources)
        response = await self._llm.complete(prompt=prompt, task_type=TaskType.DISCOVERY)

        return self._parse_candidates(response.text)

    async def search_for_sources(
        self,
        topic_name: str,
        topic_description: str,
    ) -> list[dict]:
        """Use web search to find data sources."""
        # First, get search queries from the LLM
        query_prompt = web_search_query_prompt(topic_name, topic_description)
        response = await self._llm.complete(prompt=query_prompt, task_type=TaskType.DISCOVERY)

        # Then search for each query
        all_results = []
        try:
            queries = json.loads(response.text)
        except json.JSONDecodeError:
            queries = [f"{topic_name} API data source"]

        for query in queries[:5]:  # Max 5 search queries
            results = await self._search.search(query)
            all_results.extend(results)

        return all_results

    async def validate_source(self, url: str) -> ValidatedSource | RejectedSource:
        """Validate a candidate source by making a test request."""
        # Safety check first
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            return RejectedSource(url=url, reason=reason)

        # Make a test request
        client = self._http or httpx.AsyncClient(timeout=10.0)
        should_close = self._http is None

        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "")
            sample = response.text[:2000]

            # Determine data format
            if "json" in content_type or sample.strip().startswith(("{", "[")):
                data_format = "json"
            elif "csv" in content_type:
                data_format = "csv"
            elif "xml" in content_type or sample.strip().startswith("<"):
                data_format = "xml"
            else:
                data_format = "unknown"

            # Use LLM to assess the response quality
            validation_prompt = source_validation_prompt(url, sample)
            llm_response = await self._llm.complete(
                prompt=validation_prompt, task_type=TaskType.DISCOVERY
            )

            return ValidatedSource(
                url=url,
                source_type="REST API",
                data_format=data_format,
                description=f"Validated source at {url}",
                sample_data=sample,
            )

        except httpx.HTTPStatusError as e:
            return RejectedSource(url=url, reason=f"HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            return RejectedSource(url=url, reason=f"Request failed: {e}")
        finally:
            if should_close:
                await client.aclose()

    def _parse_candidates(self, llm_text: str) -> list[CandidateSource]:
        """Parse LLM output into candidate sources."""
        try:
            # Try to extract JSON from the response
            # Find the first [ and last ] for JSON array
            start = llm_text.find("[")
            end = llm_text.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(llm_text[start:end])
                return [
                    CandidateSource(
                        url=item.get("url", ""),
                        source_type=item.get("source_type", "unknown"),
                        data_format=item.get("data_format", "unknown"),
                        description=item.get("description", ""),
                        auth_required=item.get("auth_required", False),
                    )
                    for item in data
                    if item.get("url")
                ]
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: extract URLs from text
        candidates = []
        for line in llm_text.split("\n"):
            line = line.strip()
            if "https://" in line:
                # Extract URL
                start = line.find("https://")
                end = line.find(" ", start)
                url = line[start:end] if end > start else line[start:]
                url = url.rstrip(".,;)")
                candidates.append(CandidateSource(
                    url=url,
                    source_type="unknown",
                    data_format="unknown",
                    description=line,
                ))
        return candidates
