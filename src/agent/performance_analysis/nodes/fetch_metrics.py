from __future__ import annotations

from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.core.interfaces.llm_adapter import LlmAdapter


class FetchMetricsNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PerformanceAnalysisState) -> dict:
        tool = self._llm.get_tool("query_metrics")
        if tool is None:
            return {"metric_data": "Metrics tool is not available."}

        intent = state.get("query_intent") or MetricQueryIntent()
        try:
            metric_names = intent.metric_names if intent.metric_names else None
            data = tool.invoke({
                "metric_names": metric_names,
                "lookback_seconds": intent.lookback_seconds,
                "interval_seconds": intent.interval_seconds,
                "aggregation": intent.aggregation,
                "labels": intent.labels or None,
            })
            return {"metric_data": str(data)}

        except Exception as exc:  # pylint: disable=broad-except
            return {"metric_data": f"Error fetching metrics: {exc}"}
