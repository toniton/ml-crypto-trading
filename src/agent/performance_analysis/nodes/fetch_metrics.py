from __future__ import annotations

from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.core.interfaces.llm_adapter import LlmAdapter


class FetchMetricsNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PerformanceAnalysisState) -> dict:
        intent = state.get("query_intent") or MetricQueryIntent()
        results: list[str] = []

        metrics_tool = self._llm.get_tool("query_metrics")
        if metrics_tool is not None:
            try:
                metric_names = intent.metric_names if intent.metric_names else None
                data = metrics_tool.invoke({
                    "metric_names": metric_names,
                    "lookback_seconds": intent.lookback_seconds,
                    "interval_seconds": intent.interval_seconds,
                    "aggregation": intent.aggregation,
                    "labels": intent.labels or None,
                })
                results.append(str(data))
            except Exception as exc:  # pylint: disable=broad-except
                results.append(f"Error fetching metrics: {exc}")

        attr_tool = self._llm.get_tool("get_trade_attribution")
        focus = intent.analysis_focus.lower() if intent.analysis_focus else ""
        if attr_tool is not None and any(w in focus for w in ["strategy", "attribution", "trade", "pnl", "win"]):
            try:
                lookback_days = max(1, intent.lookback_seconds // 86400)
                attr_data = attr_tool.invoke({
                    "dimension": "strategy",
                    "lookback_days": lookback_days,
                })
                results.append(str(attr_data))
            except Exception as exc:  # pylint: disable=broad-except
                results.append(f"Error fetching trade attribution: {exc}")

        if not results:
            return {"metric_data": "Metrics tool is not available."}

        return {"metric_data": "\n\n".join(results)}
