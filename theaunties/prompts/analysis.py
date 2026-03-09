"""Prompts for data analysis — change detection, comparison, trend identification."""


def change_detection_prompt(
    topic_name: str,
    previous_data: str,
    current_data: str,
    context_summary: str = "",
) -> str:
    """Generate a prompt for detecting changes between two data snapshots."""
    context_section = ""
    if context_summary:
        context_section = f"\n\nRESEARCH CONTEXT (what we've learned so far):\n{context_summary}\n"

    return f"""Compare the previous and current data for this research topic and identify all meaningful changes.

TOPIC: {topic_name}
{context_section}
PREVIOUS DATA:
{previous_data}

CURRENT DATA:
{current_data}

For each change found, provide:
1. What specific data point changed
2. The previous value
3. The current value
4. Which source reported this change
5. Whether this change is significant (and why)

Return your answer as a JSON object:
{{
  "changes": [
    {{
      "field": "what changed",
      "previous_value": "old value",
      "current_value": "new value",
      "source": "which data source",
      "significance": "high|medium|low",
      "explanation": "why this matters"
    }}
  ],
  "summary": "One sentence summarizing the overall change picture",
  "no_changes": true/false
}}

IMPORTANT: Only report changes that are actually present in the data. Do not infer or speculate about changes not reflected in the provided data."""


def data_summary_prompt(topic_name: str, collected_data: str, source_metadata: str) -> str:
    """Generate a prompt for summarizing collected raw data."""
    return f"""Summarize the following raw data collected for a research topic. Extract the key facts and findings.

TOPIC: {topic_name}

SOURCE METADATA:
{source_metadata}

COLLECTED DATA:
{collected_data}

Provide a structured summary:
1. Key facts found (with source attribution for each)
2. Notable data points or outliers
3. Any data gaps or quality issues noted

IMPORTANT: Only state facts that are directly present in the provided data. Clearly distinguish between what the data shows and any observations you make about the data. Every factual claim must cite which source it came from."""
