from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.backtest_run_spec import (
    BacktestMarketDataSpec,
    BacktestPeriodSpec,
)
from api.interfaces.walk_forward import (
    WalkForwardRunSpec,
    WalkForwardWindowSpec,
    WindowMode,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.walk_forward_application_service import (
    WalkForwardApplicationService,
)


class WalkForwardInput(BaseModel):
    action: str = Field(
        default="list",
        description="Action to perform: 'start', 'get', 'list', or 'evaluate_proposal'.",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="ID of the walk-forward run (required for action='get').",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol (e.g. 'BTC_USD') to evaluate.",
    )
    window_mode: str = Field(
        default="rolling",
        description="Window mode: 'rolling' or 'expanding'.",
    )
    train_window_days: int = Field(
        default=30,
        description="In-sample training window duration in days (default: 30).",
    )
    test_window_days: int = Field(
        default=7,
        description="Out-of-sample evaluation window duration in days (default: 7).",
    )
    step_days: int = Field(
        default=7,
        description="Step size to advance between folds in days (default: 7).",
    )
    warmup_bars: int = Field(
        default=50,
        description="Warm-up bars required for indicator initialization (default: 50).",
    )
    candidate_weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Optional candidate strategy weights to evaluate.",
    )
    baseline_weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Optional baseline strategy weights to compare against.",
    )


class WalkForwardTool(BaseTool, ApplicationLoggingMixin):
    name: str = "walk_forward"
    description: str = (
        "Executes and analyzes walk-forward validation runs. Evaluates strategy stability, "
        "detects over-fitting via Walk-Forward Efficiency (WFE), and compares out-of-sample performance."
    )
    args_schema: Type[BaseModel] = WalkForwardInput

    walk_forward_service: WalkForwardApplicationService

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, walk_forward_service: WalkForwardApplicationService):
        super().__init__(walk_forward_service=walk_forward_service)

    def _run(  # pylint: disable=arguments-differ,too-many-arguments,too-many-positional-arguments
            self,
            action: str = "list",
            run_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            window_mode: str = "rolling",
            train_window_days: int = 30,
            test_window_days: int = 7,
            step_days: int = 7,
            warmup_bars: int = 50,
            candidate_weights: Optional[dict[str, float]] = None,
            baseline_weights: Optional[dict[str, float]] = None,
    ) -> str:
        norm_action = action.strip().lower()
        self.app_logger.info("WalkForwardTool action=%s ticker=%s", norm_action, ticker_symbol)

        if norm_action in ("start", "evaluate_proposal"):
            return self._handle_start(
                ticker_symbol=ticker_symbol,
                window_mode=window_mode,
                train_window_days=train_window_days,
                test_window_days=test_window_days,
                step_days=step_days,
                warmup_bars=warmup_bars,
                candidate_weights=candidate_weights,
                baseline_weights=baseline_weights,
            )
        if norm_action == "get":
            return self._handle_get(run_id)
        return self._handle_list()

    def _handle_start(
            self,
            ticker_symbol: Optional[str],
            window_mode: str,
            train_window_days: int,
            test_window_days: int,
            step_days: int,
            warmup_bars: int,
            candidate_weights: Optional[dict[str, float]],
            baseline_weights: Optional[dict[str, float]],
    ) -> str:
        if not ticker_symbol:
            return "Error: 'ticker_symbol' is required to start a walk-forward validation run."

        mode_enum = WindowMode.EXPANDING if window_mode.lower() == "expanding" else WindowMode.ROLLING
        window_spec = WalkForwardWindowSpec(
            window_mode=mode_enum,
            train_duration_days=train_window_days,
            test_duration_days=test_window_days,
            step_size_days=step_days,
            warmup_candle_count=warmup_bars,
        )

        spec = WalkForwardRunSpec(
            ticker_symbol=ticker_symbol.strip(),
            windows=window_spec,
            data_source=BacktestMarketDataSpec(),
            period=BacktestPeriodSpec(
                start_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
                end_time=datetime.now(timezone.utc),
            ),
            candidate_weights=candidate_weights,
            baseline_weights=baseline_weights,
        )

        try:
            res = self.walk_forward_service.start_run(spec)
            run_id = res.get("run_id", "unknown")
            return (
                f"Walk-forward validation run initiated successfully.\n"
                f"- **Run ID**: `{run_id}`\n"
                f"- **Asset**: {ticker_symbol}\n"
                f"- **Window Mode**: {window_mode}\n"
                f"- **Train / Test Windows**: {train_window_days}d in-sample / "
                f"{test_window_days}d out-of-sample (step={step_days}d)\n"
                f"You can monitor results using `action='get', run_id='{run_id}'`."
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error("Failed to start walk forward run: %s", exc)
            return f"Failed to start walk-forward run: {exc}"

    def _handle_get(self, run_id: Optional[str]) -> str:
        if not run_id:
            return "Error: 'run_id' is required to fetch walk-forward run details."

        record = self.walk_forward_service.get_run(run_id)
        if not record:
            return f"Walk-forward run `{run_id}` not found."

        run_status = record.get("status", "UNKNOWN")
        summary_data = record.get("performance_summary")

        if run_status == "RUNNING":
            return f"Walk-forward run `{run_id}` is still running. Please check back shortly."
        if run_status == "FAILED":
            err = summary_data.get("error") if isinstance(summary_data, dict) else "Unknown failure"
            return f"Walk-forward run `{run_id}` failed: {err}"
        if not summary_data:
            return f"Walk-forward run `{run_id}` has status `{run_status}`, but no performance summary is available."

        return self._format_summary(run_id, record.get("ticker_symbol", "UNKNOWN"), summary_data)

    def _handle_list(self) -> str:
        runs = self.walk_forward_service.list_runs(limit=10)
        if not runs:
            return "No previous walk-forward runs found."

        lines = ["### 📜 Recent Walk-Forward Runs\n"]
        for r in runs:
            rid = r.get("run_id", "N/A")
            sym = r.get("ticker_symbol", "N/A")
            st = r.get("status", "N/A")
            summary = r.get("performance_summary")
            metrics_str = ""
            if isinstance(summary, dict) and "stability_classification" in summary:
                metrics_str = (
                    f" | OOS Return: {summary.get('out_of_sample_return_pct', 0.0):+.2f}%"
                    f" | WFE: {summary.get('walk_forward_efficiency_ratio', 0.0):.2f}"
                    f" | Status: {summary.get('stability_classification')}"
                )
            lines.append(f"- `{rid}` ({sym}) [{st}]{metrics_str}")
        return "\n".join(lines)

    @staticmethod
    def _format_summary(run_id: str, ticker: str, summary: dict[str, Any]) -> str:  # pylint: disable=too-many-locals
        stability = summary.get("stability_classification", "UNKNOWN")
        oos_ret = summary.get("out_of_sample_return_pct", 0.0)
        is_ret = summary.get("in_sample_return_pct", 0.0)
        wfe = summary.get("walk_forward_efficiency_ratio", 0.0)
        max_dd = summary.get("max_out_of_sample_drawdown_pct", 0.0)
        prof_ratio = summary.get("profitable_fold_ratio", 0.0)
        prof_folds = summary.get("profitable_folds", 0)
        tot_folds = summary.get("total_folds", 0)
        base_ret = summary.get("baseline_return_pct", 0.0)
        excess_ret = summary.get("excess_return_vs_baseline_pct", 0.0)

        lines = [
            f"### 🛡️ Walk-Forward Validation Report: `{run_id}` ({ticker})\n",
            f"- **Stability Classification**: **{stability}**",
            f"- **Cumulative Out-of-Sample Return**: {oos_ret:+.2f}% (vs In-Sample: {is_ret:+.2f}%)",
            f"- **Walk-Forward Efficiency (WFE)**: {wfe:.2f} (values > 0.5 indicate strong generalization)",
            f"- **Max Out-of-Sample Drawdown**: {max_dd:.2f}%",
            f"- **Profitable Folds**: {prof_folds}/{tot_folds} ({prof_ratio * 100:.1f}%)",
            (
                f"- **Baseline Comparison**: Proposed: {oos_ret:+.2f}% vs "
                f"Unchanged Baseline: {base_ret:+.2f}% (Delta: {excess_ret:+.2f}%)"
            ),
        ]

        folds = summary.get("folds", [])
        if isinstance(folds, list) and folds:
            lines.append("\n#### Fold Breakdown:")
            for f in folds:
                f_idx = f.get("fold_index", 0)
                f_is_ret = f.get("in_sample_return_pct", 0.0)
                f_oos_ret = f.get("out_of_sample_return_pct", 0.0)
                f_trades = f.get("out_of_sample_trades", 0)
                f_wr = f.get("out_of_sample_win_rate_pct", 0.0)
                lines.append(
                    f"- **Fold #{f_idx}**: IS Return: {f_is_ret:+.2f}% | OOS Return: {f_oos_ret:+.2f}% "
                    f"({f_trades} trades, {f_wr:.1f}% WR)"
                )

        return "\n".join(lines)
