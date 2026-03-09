"""Prompts for chat interactions — topic parsing, refinement, Q&A."""


def topic_parsing_prompt(user_message: str) -> str:
    """Generate a prompt for parsing a user's topic description."""
    return f"""Parse the user's message to extract a research topic. The user is describing what they want an autonomous research agent to monitor on their behalf.

USER MESSAGE: {user_message}

Extract and return a JSON object:
{{
  "name": "Short topic name (3-6 words)",
  "description": "Detailed description of what to research and monitor",
  "key_aspects": ["list", "of", "specific", "things", "to", "track"],
  "suggested_schedule": "cron expression (default: 0 6 * * * for daily at 6am)",
  "clarifying_questions": ["Any questions to ask the user to improve the research plan"]
}}

If the message is too vague to create a useful topic, set "needs_clarification" to true and provide specific clarifying_questions."""


def topic_confirmation_prompt(topic_name: str, topic_description: str, key_aspects: list[str]) -> str:
    """Generate a prompt for confirming a topic with the user."""
    aspects = "\n".join(f"  - {a}" for a in key_aspects)
    return f"""Generate a confirmation message for the user about their research topic. Be conversational and clear.

TOPIC NAME: {topic_name}
DESCRIPTION: {topic_description}
KEY ASPECTS TO TRACK:
{aspects}

Write a brief, friendly message that:
1. Confirms what you understood about their research interest
2. Lists the key things you'll be tracking
3. Mentions you'll discover data sources automatically
4. Asks if this looks right or if they want to adjust anything"""


def refinement_prompt(
    user_message: str,
    topic_name: str,
    topic_description: str,
    current_context: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Generate a prompt for handling a user refinement message."""
    history_section = ""
    if chat_history:
        history_lines = []
        for msg in chat_history[-10:]:  # Last 10 messages for context
            history_lines.append(f"{msg['role'].upper()}: {msg['message']}")
        history_section = "\nRECENT CHAT HISTORY:\n" + "\n".join(history_lines) + "\n"

    return f"""The user is refining their research topic. Understand their feedback and determine what changes to make.

CURRENT TOPIC: {topic_name}
CURRENT DESCRIPTION: {topic_description}
CURRENT CONTEXT: {current_context}
{history_section}
USER'S NEW MESSAGE: {user_message}

Determine what the user wants to change and return a JSON object:
{{
  "action": "refine_topic|add_aspect|remove_aspect|change_schedule|ask_question|general_response",
  "changes": {{
    "description": "updated description if changed",
    "add_aspects": ["new aspects to track"],
    "remove_aspects": ["aspects to stop tracking"],
    "schedule": "new cron expression if changed"
  }},
  "response": "What to say back to the user confirming the change"
}}"""


def qa_prompt(
    user_question: str,
    topic_name: str,
    latest_findings: str,
    context_summary: str,
    source_list: str,
) -> str:
    """Generate a prompt for answering user questions about their research."""
    return f"""The user is asking a question about their research topic. Answer based ONLY on the data and context available.

TOPIC: {topic_name}

USER QUESTION: {user_question}

LATEST FINDINGS:
{latest_findings}

ACCUMULATED CONTEXT:
{context_summary}

REGISTERED SOURCES:
{source_list}

Answer the user's question conversationally. CRITICAL RULES:
1. Only state facts that are in the provided data. If you don't know, say so.
2. Cite sources for any factual claims.
3. If the question is about something outside the monitored data, suggest how the research could be expanded to cover it.
4. Be honest about data gaps or limitations."""
