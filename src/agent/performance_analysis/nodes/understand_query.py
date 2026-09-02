from __future__ import annotations

from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.prompts import UNDERSTAND_QUERY_PROMPT
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.core.interfaces.llm_adapter import LlmAdapter


class UnderstandMetricQueryNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PerformanceAnalysisState) -> dict:
        prompt = self._format_prompt(state)
        intent = self._llm.generate_structured(
            MetricQueryIntent, prompt, UNDERSTAND_QUERY_PROMPT
        )
        return {"query_intent": intent}

    @staticmethod
    def _format_prompt(state: PerformanceAnalysisState) -> str:
        lines = [f"User query: {state.get('user_prompt', '')}"]
        history = state.get("history", [])
        if history:
            lines.append("CONVERSATION HISTORY")
            for turn in history:
                lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines)
