from __future__ import annotations

from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.prompts import ANALYZE_METRICS_PROMPT
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.core.interfaces.llm_adapter import LlmAdapter


class AnalyzeMetricsNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PerformanceAnalysisState) -> dict:
        intent = state.get("query_intent") or MetricQueryIntent()
        prompt = (
            f"{ANALYZE_METRICS_PROMPT}\n\n"
            f"User Prompt: {state.get('user_prompt', '')}\n"
            f"Focus Area: {intent.analysis_focus}\n\n"
            f"Retrieved Metrics:\n{state.get('metric_data', 'No data available.')}"
        )
        analysis = self._llm.generate(prompt)
        return {"analysis_summary": analysis}
