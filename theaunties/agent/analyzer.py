"""Analyzer — change detection and data comparison between runs."""

import json
import logging
from dataclasses import dataclass, field

from theaunties.llm.router import LLMRouter, TaskType
from theaunties.prompts.analysis import change_detection_prompt, data_summary_prompt

logger = logging.getLogger(__name__)


@dataclass
class Change:
    """A detected change between two data snapshots."""
    field: str
    previous_value: str
    current_value: str
    source: str
    significance: str = "medium"  # high, medium, low
    explanation: str = ""


@dataclass
class AnalysisResult:
    """Result of analyzing collected data."""
    changes: list[Change] = field(default_factory=list)
    summary: str = ""
    no_changes: bool = False
    raw_analysis: str = ""


@dataclass
class DataSummary:
    """Summary of collected raw data."""
    text: str = ""
    key_facts: list[str] = field(default_factory=list)
    source_attributions: dict = field(default_factory=dict)


class Analyzer:
    """Analyzes data and detects changes between research runs."""

    def __init__(self, llm_router: LLMRouter):
        self._llm = llm_router

    async def detect_changes(
        self,
        topic_name: str,
        previous_data: str,
        current_data: str,
        context_summary: str = "",
    ) -> AnalysisResult:
        """Detect changes between previous and current data snapshots."""
        if not previous_data:
            return AnalysisResult(
                no_changes=True,
                summary="First run — no previous data to compare against.",
            )

        if previous_data == current_data:
            return AnalysisResult(
                no_changes=True,
                summary="No changes detected between runs.",
            )

        prompt = change_detection_prompt(
            topic_name=topic_name,
            previous_data=previous_data,
            current_data=current_data,
            context_summary=context_summary,
        )

        response = await self._llm.complete(
            prompt=prompt,
            task_type=TaskType.DATA_ANALYSIS,
        )

        return self._parse_changes(response.text)

    async def summarize_data(
        self,
        topic_name: str,
        collected_data: str,
        source_metadata: str,
    ) -> DataSummary:
        """Summarize raw collected data into structured findings."""
        prompt = data_summary_prompt(
            topic_name=topic_name,
            collected_data=collected_data,
            source_metadata=source_metadata,
        )

        response = await self._llm.complete(
            prompt=prompt,
            task_type=TaskType.DATA_ANALYSIS,
        )

        return DataSummary(text=response.text)

    def _parse_changes(self, llm_text: str) -> AnalysisResult:
        """Parse LLM output into structured changes."""
        try:
            # Try to extract JSON
            start = llm_text.find("{")
            end = llm_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(llm_text[start:end])
                changes = [
                    Change(
                        field=c.get("field", "unknown"),
                        previous_value=str(c.get("previous_value", "")),
                        current_value=str(c.get("current_value", "")),
                        source=c.get("source", "unknown"),
                        significance=c.get("significance", "medium"),
                        explanation=c.get("explanation", ""),
                    )
                    for c in data.get("changes", [])
                ]
                return AnalysisResult(
                    changes=changes,
                    summary=data.get("summary", ""),
                    no_changes=data.get("no_changes", len(changes) == 0),
                    raw_analysis=llm_text,
                )
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: use the raw text as the summary
        return AnalysisResult(
            summary=llm_text[:500],
            raw_analysis=llm_text,
        )
