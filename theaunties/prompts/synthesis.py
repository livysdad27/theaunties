"""Prompts for document synthesis — daily research doc writing."""


def daily_doc_prompt(
    topic_name: str,
    date: str,
    summary_data: str,
    changes: str,
    source_statuses: str,
    context_summary: str = "",
    previous_doc_summary: str = "",
) -> str:
    """Generate a prompt for writing the daily research document."""
    context_section = ""
    if context_summary:
        context_section = f"\nRESEARCH CONTEXT (accumulated knowledge):\n{context_summary}\n"

    prev_section = ""
    if previous_doc_summary:
        prev_section = f"\nPREVIOUS DOC SUMMARY (for continuity):\n{previous_doc_summary}\n"

    return f"""Write a daily research document for the topic below. This document will be delivered to the user as their daily research digest.

TOPIC: {topic_name}
DATE: {date}
{context_section}{prev_section}
DATA SUMMARY:
{summary_data}

CHANGES DETECTED:
{changes}

SOURCE STATUS:
{source_statuses}

Write the document with these exact sections:

## Summary
2-3 sentences summarizing today's key findings. What does the user need to know?

## What Changed
Bullet points showing specific changes since the last run. Include before/after values where applicable. Each change must cite its source.

## Detailed Findings
Organized findings from each data source. Each finding must have an inline citation in the format [Source: source_name].

## Sources
Table or list of all sources queried today, with their status (success/failure) and when they were last checked.

## Agent Notes
Any observations about source quality, data gaps, suggested research adjustments, or emerging trends.

CRITICAL RULES — FOLLOW THESE EXACTLY:
1. ONLY include information that is present in the provided data. Never invent, extrapolate, or hallucinate facts.
2. Every factual claim MUST have a source citation. No uncited facts.
3. If a source failed, say so explicitly. Do not fill in missing data with guesses.
4. Clearly separate FACTS (from data) from OBSERVATIONS (your analysis).
5. If there is insufficient data to draw conclusions, say "Insufficient data" rather than speculating.
6. Use specific numbers and values from the data, not vague language like "increased slightly."
"""


def confidence_assessment_prompt(findings: str, source_count: int) -> str:
    """Generate a prompt for assessing confidence in findings."""
    return f"""Assess the confidence level of each finding below based on:
- Number of corroborating sources
- Source reliability
- Data freshness
- Consistency of data

FINDINGS:
{findings}

TOTAL SOURCES QUERIED: {source_count}

For each finding, assign:
- HIGH confidence: Multiple reliable sources agree, data is fresh
- MEDIUM confidence: Single reliable source, or multiple sources with minor discrepancies
- LOW confidence: Single source, data may be stale, or notable discrepancies

Return a JSON array with each finding and its confidence level + reasoning."""
