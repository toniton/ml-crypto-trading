from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from api.interfaces.promotion import (
    SimulationReportSummary,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresSimulatedRunRepository,
    PostgresSimulationReportRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.promotion_policy import PromotionPolicy


class SimulationReportService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            policy: Optional[PromotionPolicy] = None,
    ) -> None:
        self._db_manager = db_manager
        self._policy = policy or PromotionPolicy()

    def generate_and_save_report(
            self,
            run_id: str,
            trades: list[dict[str, Any]],
            equity_curve: list[float],
            operational_diagnostics: Optional[dict[str, Any]] = None,
            baseline_trades: Optional[list[dict[str, Any]]] = None,
            baseline_equity_curve: Optional[list[float]] = None,
    ) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Simulated run '{run_id}' not found.")

        diagnostics = operational_diagnostics or {}
        runtime_errors = int(diagnostics.get("runtime_errors_count", 0))

        summary = self._calculate_metrics(trades, equity_curve, runtime_errors)

        baseline_summary = None
        if baseline_trades is not None and baseline_equity_curve is not None:
            baseline_summary = self._calculate_metrics(baseline_trades, baseline_equity_curve, 0)
            summary.baseline_return_diff_pct = round(summary.net_return_pct - baseline_summary.net_return_pct, 4)

        gate_b_result = self._policy.evaluate_gate_b(
            metrics=summary.model_dump(mode="json"),
            baseline_metrics=baseline_summary.model_dump(mode="json") if baseline_summary else None,
        )

        config_hash = run.get("config_hash") or hashlib.sha256(
            json.dumps(run.get("execution_spec", {}), sort_keys=True).encode()
        ).hexdigest()

        report_payload = {
            "identity": {
                "experiment_id": run["experiment_id"],
                "candidate_id": run["candidate_id"],
                "candidate_commit": run["candidate_commit"],
                "run_id": run_id,
                "config_hash": config_hash,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "test_conditions": {
                "market_data_spec": run.get("market_data_spec", {}),
                "execution_spec": run.get("execution_spec", {}),
            },
            "performance": summary.model_dump(mode="json"),
            "baseline_comparison": {
                "baseline_available": baseline_summary is not None,
                "baseline_net_return_pct": baseline_summary.net_return_pct if baseline_summary else None,
                "return_delta_pct": summary.baseline_return_diff_pct,
            },
            "strategy_attribution": self._calculate_strategy_attribution(trades),
            "operational_diagnostics": {
                "missed_ticks": diagnostics.get("missed_ticks", 0),
                "order_simulation_failures": diagnostics.get("order_simulation_failures", 0),
                "runtime_errors_count": runtime_errors,
                "error_details": diagnostics.get("error_details", []),
            },
            "limitations": [
                "Paper trading model assumes standard slippage and constant order fill probability.",
                "Market impact of larger hypothetical order sizing is not simulated.",
            ],
            "decision": {
                "gate_name": gate_b_result.gate_name,
                "decision": gate_b_result.decision.value,
                "checks": [c.model_dump(mode="json") for c in gate_b_result.checks],
            },
        }

        report_id = f"rep_{uuid.uuid4().hex[:12]}"
        with self._db_manager.get_unit_of_work() as uow:
            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            report_repo.save_report(
                report_id=report_id,
                run_id=run_id,
                config_hash=config_hash,
                decision=gate_b_result.decision.value,
                summary_metrics=summary.model_dump(mode="json"),
                report_payload=report_payload,
            )

        return {
            "report_id": report_id,
            "run_id": run_id,
            "decision": gate_b_result.decision.value,
            "summary_metrics": summary.model_dump(mode="json"),
            "report_payload": report_payload,
        }

    def get_report_by_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            return report_repo.get_report_by_run(run_id)

    @staticmethod
    def _calculate_metrics(
            trades: list[dict[str, Any]],
            equity_curve: list[float],
            runtime_errors: int,
    ) -> SimulationReportSummary:
        executed_trades = len(trades)
        if not equity_curve:
            return SimulationReportSummary(
                net_return_pct=0.0,
                max_drawdown_pct=0.0,
                executed_trades=executed_trades,
                win_rate_pct=0.0,
                profit_factor=0.0,
                baseline_return_diff_pct=0.0,
                runtime_errors_count=runtime_errors,
            )

        start_bal = equity_curve[0]
        end_bal = equity_curve[-1]
        net_return_pct = round(((end_bal - start_bal) / start_bal) * 100.0, 4) if start_bal > 0 else 0.0

        # Calculate maximum drawdown
        peak = start_bal
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            if peak > 0:
                dd = ((peak - val) / peak) * 100.0
                if dd > max_dd:
                    max_dd = dd

        # Trade stats
        wins = [t for t in trades if float(t.get("pnl", 0.0)) > 0]
        losses = [t for t in trades if float(t.get("pnl", 0.0)) < 0]
        win_rate_pct = round((len(wins) / executed_trades) * 100.0, 2) if executed_trades > 0 else 0.0

        total_gain = sum(float(t.get("pnl", 0.0)) for t in wins)
        total_loss = abs(sum(float(t.get("pnl", 0.0)) for t in losses))
        profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else (round(total_gain, 2) if total_gain > 0 else 1.0)

        return SimulationReportSummary(
            net_return_pct=net_return_pct,
            max_drawdown_pct=round(max_dd, 4),
            executed_trades=executed_trades,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            baseline_return_diff_pct=0.0,
            runtime_errors_count=runtime_errors,
        )

    @staticmethod
    def _calculate_strategy_attribution(trades: list[dict[str, Any]]) -> dict[str, Any]:
        by_strategy: dict[str, dict[str, Any]] = {}
        for t in trades:
            strat = t.get("strategy_name") or "default"
            pnl = float(t.get("pnl", 0.0))
            if strat not in by_strategy:
                by_strategy[strat] = {"trade_count": 0, "total_pnl": 0.0, "wins": 0}
            by_strategy[strat]["trade_count"] += 1
            by_strategy[strat]["total_pnl"] = round(by_strategy[strat]["total_pnl"] + pnl, 4)
            if pnl > 0:
                by_strategy[strat]["wins"] += 1
        return by_strategy
