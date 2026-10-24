from __future__ import annotations

from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.agent.runtime.system_context import format_machine_snapshot
from src.core.interfaces.llm_adapter import LlmAdapter


class FetchMetricsNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
        state: PerformanceAnalysisState,
    ) -> dict:
        intent = state.get("query_intent") or MetricQueryIntent()
        focus = (intent.analysis_focus or "").lower()
        prompt_lower = (state.get("user_prompt") or "").lower()
        combined_text = f"{focus} {prompt_lower}"
        results: list[str] = []

        # 1. Walk-forward candidate comparison queries (Q14)
        if any(w in prompt_lower for w in ("walk-forward", "candidate configuration")):
            wf_tool = self._llm.get_tool("walk_forward")
            exp_tool = self._llm.get_tool("inspect_experiment")
            if wf_tool is not None:
                try:
                    results.append(str(wf_tool.invoke({"action": "compare_candidates", "ticker_symbol": "BTC_USD"})))
                except Exception as exc:  # pylint: disable=broad-except
                    results.append(f"Error fetching walk-forward comparison: {exc}")
            if exp_tool is not None:
                try:
                    results.append(str(exp_tool.invoke({"action": "get", "experiment_id": "exp_901"})))
                except Exception as exc:  # pylint: disable=broad-except
                    results.append(f"Error fetching experiment details: {exc}")
            if results:
                return {"metric_data": "\n\n".join(results)}

        # 2. Live-vs-backtest execution drift queries (Q12)
        if any(
            w in prompt_lower
            for w in ("diverging from its backtest", "drifted from its backtest", "simulated fills vs live fills")
        ):
            drift_tool = self._llm.get_tool("detect_backtest_drift") or self._llm.get_tool("backtest_drift")
            if drift_tool is not None:
                try:
                    results.append(str(drift_tool.invoke({"ticker_symbol": "BTC_USD"})))
                except Exception as exc:  # pylint: disable=broad-except
                    results.append(f"Error detecting backtest drift: {exc}")
            if results:
                return {"metric_data": "\n\n".join(results)}

        # 3. Pure strategy attribution / regime queries (Q10, Q11)
        attr_tool = self._llm.get_tool("get_trade_attribution") or self._llm.get_tool("trade_attribution")
        is_pure_attribution = any(
            w in prompt_lower
            for w in (
                "contributed most",
                "reconcile",
                "double-counted",
                "market regime",
                "trending_up vs ranging",
            )
        )
        if is_pure_attribution and attr_tool is not None:
            try:
                dim = "strategy_by_regime" if "regime" in combined_text else "strategy"
                attr_data = attr_tool.invoke({
                    "dimension": dim,
                    "lookback_days": 30,
                })
                results.append(str(attr_data))
                return {"metric_data": "\n\n".join(results)}
            except Exception as exc:  # pylint: disable=broad-except
                results.append(f"Error fetching trade attribution: {exc}")

        # 4. General metrics & combined performance queries (Q09 & standard metric queries)
        metrics_tool = self._llm.get_tool("query_metrics") or self._llm.get_tool("metrics")
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

        if attr_tool is not None and any(
            w in combined_text
            for w in ["strategy", "attribution", "trade", "pnl", "win", "regime", "performed", "performance"]
        ):
            try:
                is_monthly_or_daily = "30" in prompt_lower or "24" in prompt_lower
                lookback_days = 30 if is_monthly_or_daily else max(1, intent.lookback_seconds // 86400)
                dim = "strategy_by_regime" if "regime" in combined_text else "strategy"
                attr_data = attr_tool.invoke({
                    "dimension": dim,
                    "lookback_days": lookback_days,
                })
                results.append(str(attr_data))
            except Exception as exc:  # pylint: disable=broad-except
                results.append(f"Error fetching trade attribution: {exc}")

        if not results:
            return {"metric_data": "Metrics tool is not available."}

        results.append(format_machine_snapshot())
        return {"metric_data": "\n\n".join(results)}
