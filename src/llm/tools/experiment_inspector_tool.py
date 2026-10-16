from __future__ import annotations

from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class ExperimentInspectorInput(BaseModel):
    action: str = Field(
        default="get",
        description="Action: 'get' (inspect experiment provenance & candidates), 'list', or 'evaluate_justification'.",
    )
    experiment_id: Optional[str] = Field(
        default=None,
        description="Experiment ID (e.g. 'exp_901') when action='get'.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol (e.g. 'BTC_USD') when evaluating experiment justification.",
    )


class ExperimentInspectorTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "inspect_experiment"
    description: str = (
        "Inspects experiment provenance (triggered_by event, causal evidence, base commit, branch, "
        "candidate run bindings, walk-forward results) and evaluates whether asset inactivity or "
        "live-vs-backtest drift justifies triggering a new research experiment."
    )
    args_schema: Type[BaseModel] = ExperimentInspectorInput
    experiment_service: Any = None
    health_monitor: Any = None
    activity_tracker: Any = None
    drift_detector: Any = None

    def __init__(
            self,
            experiment_service: Any = None,
            health_monitor: Any = None,
            activity_tracker: Any = None,
            drift_detector: Any = None,
    ):
        super().__init__(
            experiment_service=experiment_service,
            health_monitor=health_monitor,
            activity_tracker=activity_tracker,
            drift_detector=drift_detector,
        )

    def _run(  # pylint: disable=arguments-differ
            self,
            action: str = "get",
            experiment_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
    ) -> str:
        norm = action.strip().lower()
        if norm == "evaluate_justification":
            return self._evaluate_justification(ticker_symbol)
        if norm == "list":
            return self._list_experiments(ticker_symbol)
        return self._get_experiment(experiment_id, ticker_symbol)

    def _get_experiment(self, experiment_id: Optional[str], ticker_symbol: Optional[str]) -> str:
        if self.experiment_service is None:
            return "Experiment service is not available."
        if not experiment_id:
            exps = self.experiment_service.list_experiments(limit=10)
            if ticker_symbol:
                target = ticker_symbol.strip().upper()
                exps = [e for e in exps if str(e.get("ticker_symbol", "")).upper() == target]
            if not exps:
                return "No experiments found."
            exp = exps[0]
        else:
            exp = self.experiment_service.get_experiment(experiment_id.strip())
            if not exp:
                return f"Experiment '{experiment_id}' not found."

        return self._format_experiment(exp)

    def _list_experiments(self, ticker_symbol: Optional[str]) -> str:
        if self.experiment_service is None:
            return "Experiment service is not available."
        exps = self.experiment_service.list_experiments(limit=20)
        if ticker_symbol:
            target = ticker_symbol.strip().upper()
            exps = [e for e in exps if str(e.get("ticker_symbol", "")).upper() == target]
        if not exps:
            return "No experiments found."
        lines = [f"Experiments ({len(exps)}):"]
        for e in exps:
            spec = e.get("spec") or {}
            trig = spec.get("triggered_by") or {}
            trig_str = (
                f" | Trigger: {trig.get('trigger_type', 'MANUAL')} ({trig.get('source_event_id', 'N/A')})"
                if trig else ""
            )
            lines.append(
                f"- {e.get('experiment_id')}: {e.get('name')} ({e.get('ticker_symbol')}) "
                f"[Status: {e.get('status')}, Base Commit: {e.get('base_commit_hash')}]{trig_str}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_experiment(exp: dict[str, Any]) -> str:
        spec = exp.get("spec") or {}
        trig = spec.get("triggered_by") or {}
        bindings = exp.get("run_bindings") or []
        report = exp.get("report") or {}

        lines = [
            f"=== Experiment {exp.get('experiment_id')} ({exp.get('name')}) ===",
            f"Asset: {exp.get('ticker_symbol')}",
            f"Status: {exp.get('status')}",
            f"Base Configuration Commit: {exp.get('base_commit_hash')}",
            f"Experiment Branch ID: {exp.get('branch_id')}",
        ]
        if trig:
            lines.append("\n[Trigger & Provenance]")
            lines.append(f"  Trigger Type: {trig.get('trigger_type', 'UNKNOWN')}")
            lines.append(f"  Source Event ID: {trig.get('source_event_id', 'N/A')}")
            lines.append(f"  Causal Evidence: {trig.get('evidence_summary', 'N/A')}")
            if trig.get("detected_at"):
                lines.append(f"  Detected At: {trig.get('detected_at')}")
        else:
            lines.append("\n[Trigger & Provenance]\n  Trigger Type: MANUAL_OPERATOR_REQUEST")

        if bindings:
            lines.append(f"\n[Candidate Run Bindings ({len(bindings)})]")
            for b in bindings:
                lines.append(
                    f"  - Candidate `{b.get('candidate_id')}`: Status={b.get('status')}, "
                    f"Backtest Session={b.get('backtest_session_id') or 'N/A'}, "
                    f"Walk-Forward Run={b.get('walk_forward_run_id') or 'N/A'}"
                )

        if report:
            lines.append("\n[Experiment Evaluation Summary]")
            if report.get("recommended_candidate_id"):
                lines.append(f"  Recommended Robust Candidate: {report.get('recommended_candidate_id')}")
            if report.get("exploratory_winner_id"):
                lines.append(f"  Exploratory (In-Sample) Winner: {report.get('exploratory_winner_id')}")
            if report.get("summary"):
                lines.append(f"  Conclusion: {report.get('summary')}")

        return "\n".join(lines)

    def _evaluate_justification(  # pylint: disable=too-many-branches
            self,
            ticker_symbol: Optional[str],
    ) -> str:
        symbol = (ticker_symbol or "BTC_USD").strip().upper()
        lines = [f"=== Experiment Justification Triage for {symbol} ==="]

        operational_block = False
        if self.health_monitor is not None:
            snap = self.health_monitor.snapshot
            asset_conds = [
                c for c in snap.active_conditions
                if c.scope.identifier.upper() in (symbol, "GLOBAL")
            ]
            lines.append(f"1. Operational Health State: {snap.state.value}")
            if asset_conds:
                operational_block = True
                cond_desc = ", ".join(
                    f"{c.condition.value} (measured={c.measured_value}, limit={c.threshold})"
                    for c in asset_conds
                )
                lines.append(f"   Active Operational Conditions: {cond_desc}")

        if self.activity_tracker is not None:
            st = self.activity_tracker.state_for(symbol)
            if st is None or st.last_market_data_at is None:
                operational_block = True
                lines.append("2. Activity Stage Classification: NO_MARKET_DATA (Operational data feed stall)")
            elif st.last_evaluation_at is None:
                operational_block = True
                lines.append("2. Activity Stage Classification: NO_STRATEGY_ACTIVITY (Evaluation pipeline stalled)")
            elif st.last_signal_at is None:
                lines.append(
                    "2. Activity Stage Classification: NO_SIGNALS (Low strategy signal frequency / quorum not met)"
                )
            elif st.last_order_at is None:
                lines.append("2. Activity Stage Classification: NO_ORDERS (Blocked by risk guard or sizing limits)")
            else:
                lines.append("2. Activity Stage Classification: ACTIVE_PIPELINE (Data, signals, and orders flowing)")

        drifted = False
        if self.drift_detector is not None:
            try:
                report = self.drift_detector.detect(symbol)
                drifted = report.drifted
                lines.append(
                    f"3. Backtest vs Live Drift: Drifted={report.drifted} "
                    f"(Fill Drift={report.fill_count_drift}, Qty Drift={report.quantity_drift}, "
                    f"Price Drift={report.price_drift})"
                )
            except Exception as exc:  # pylint: disable=broad-except
                lines.append(f"3. Backtest vs Live Drift: Could not compute ({exc})")

        if operational_block:
            lines.append(
                "\nConclusion: DO NOT TRIGGER EXPERIMENT. Inactivity is caused by an operational/data-feed issue "
                "(e.g. NO_MARKET_DATA or unhealthy runtime condition), NOT strategy decay."
            )
        elif drifted:
            lines.append(
                "\nConclusion: EXPERIMENT JUSTIFIED. Operational pipeline is healthy, but live execution/performance "
                "has significantly drifted from backtest expectations."
            )
        else:
            lines.append(
                "\nConclusion: EXPERIMENT NOT REQUIRED. Pipeline is healthy and no statistically significant "
                "performance deterioration or drift was detected."
            )
        return "\n".join(lines)
