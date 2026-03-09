"""Prompts for source discovery — brainstorming, URL extraction, validation."""


def source_brainstorm_prompt(topic_name: str, topic_description: str, existing_sources: list[str] | None = None) -> str:
    """Generate a prompt for brainstorming data sources for a topic."""
    existing = ""
    if existing_sources:
        existing = (
            "\n\nThe following sources are already registered (do not suggest these again):\n"
            + "\n".join(f"- {s}" for s in existing_sources)
        )

    return f"""You are a research data source specialist. Given a research topic, identify public programmatic data sources (APIs, open datasets, government data feeds, structured web endpoints) that provide real, verifiable data relevant to the topic.

TOPIC: {topic_name}
DESCRIPTION: {topic_description}
{existing}

For each source, provide:
1. The full API endpoint or dataset URL (must be HTTPS)
2. The type (REST API, CSV feed, JSON endpoint, XML feed, etc.)
3. The data format returned (json, csv, xml, etc.)
4. A brief description of what data it provides
5. Whether authentication is required (prefer free, no-auth sources)

Return your answer as a JSON array of objects with keys: url, source_type, data_format, description, auth_required.

Only suggest sources that:
- Are publicly accessible via HTTPS
- Return structured, parseable data (not HTML web pages)
- Are maintained and likely to be available
- Provide data directly relevant to the topic

Do NOT suggest:
- Web scraping targets
- Sources requiring paid subscriptions
- Sources with complex OAuth flows
- Internal or private network endpoints"""


def source_validation_prompt(url: str, response_sample: str) -> str:
    """Generate a prompt to validate whether a source returns useful data."""
    return f"""Analyze this API response and determine if it provides useful, structured data.

URL: {url}
RESPONSE SAMPLE (first 2000 chars):
{response_sample[:2000]}

Answer with a JSON object:
{{
  "is_valid": true/false,
  "data_format": "json|csv|xml|other",
  "description": "Brief description of what data this provides",
  "rejection_reason": "Only if is_valid is false — explain why"
}}"""


def web_search_query_prompt(topic_name: str, topic_description: str) -> str:
    """Generate search queries for finding data sources."""
    return f"""Generate 3-5 web search queries to find public APIs and datasets related to this topic. Focus on finding programmatic data sources, not general web pages.

TOPIC: {topic_name}
DESCRIPTION: {topic_description}

Return a JSON array of search query strings. Example:
["USGS water data API", "weather forecast API free", "lake water temperature dataset"]"""
