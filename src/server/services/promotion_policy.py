from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from api.interfaces.promotion import (
    GateCheckItem,
    GateCheckStatus,
    GateDecision,
    GateEvaluationResult,
)


class PromotionPolicy:
    def __init__(
            self,
            min_trades: int = 5,
            max_drawdown_pct: float = 15.0,
            require_prior_backtest: bool = True,
    ) -> None:
        self.min_trades = min_trades
        self.max_drawdown_pct = max_drawdown_pct
        self.require_prior_backtest = require_prior_backtest

    def evaluate_gate_a(
            self,
            candidate: dict[str, Any],
            experiment: dict[str, Any],
            base_commit: Optional[str] = None,
            run_bindings: Optional[list[dict[str, Any]]] = None,
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        # 1. Configuration schema check
        weights = candidate.get("strategy_weights")
        has_weights = isinstance(weights, dict) and len(weights) > 0
        checks.append(
            GateCheckItem(
                name="configuration_valid",
                status=GateCheckStatus.PASSED if has_weights else GateCheckStatus.FAILED,
                message="Candidate contains valid strategy configuration."
                if has_weights
                else "Candidate strategy configuration is missing or empty.",
                value=len(weights) if isinstance(weights, dict) else 0,
            )
        )

        # 2. Source commit traceability
        source_commit = candidate.get("candidate_commit_hash") or base_commit or experiment.get("base_commit_hash")
        has_commit = bool(source_commit and len(str(source_commit)) >= 6)
        checks.append(
            GateCheckItem(
                name="source_commit_traceable",
                status=GateCheckStatus.PASSED if has_commit else GateCheckStatus.FAILED,
                message=f"Tied to source commit {str(source_commit)[:8]}."
                if has_commit
                else "Source commit is unknown or uncommitted.",
                value=source_commit,
            )
        )

        # 3. Prior backtest verification
        bindings = run_bindings or experiment.get("run_bindings", [])
        has_backtest = bool(bindings and len(bindings) > 0)
        checks.append(
            GateCheckItem(
                name="prior_backtest_exists",
                status=GateCheckStatus.PASSED if (has_backtest or not self.require_prior_backtest) else GateCheckStatus.FAILED,
                message=f"Found {len(bindings)} prior test run(s)."
                if has_backtest
                else "No prior backtest run bindings found for candidate.",
                value=len(bindings),
            )
        )

        all_passed = all(c.status == GateCheckStatus.PASSED for c in checks)
        decision = GateDecision.PASS if all_passed else GateDecision.FAIL

        return GateEvaluationResult(
            gate_name="Gate A: Experiment to Simulation",
            decision=decision,
            checks=checks,
            evaluated_at=datetime.now(timezone.utc),
        )

    def evaluate_gate_b(
            self,
            metrics: dict[str, Any],
            baseline_metrics: Optional[dict[str, Any]] = None,
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        trades = int(metrics.get("executed_trades", 0))
        max_dd = float(metrics.get("max_drawdown_pct", 0.0))
        runtime_errors = int(metrics.get("runtime_errors_count", 0))
        net_return = float(metrics.get("net_return_pct", 0.0))

        baseline_return = float(baseline_metrics.get("net_return_pct", 0.0)) if baseline_metrics else 0.0
        return_diff = net_return - baseline_return

        # 1. Minimum trades check
        trades_passed = trades >= self.min_trades
        checks.append(
            GateCheckItem(
                name="minimum_executed_trades",
                status=GateCheckStatus.PASSED if trades_passed else GateCheckStatus.FAILED,
                message=f"Executed {trades} trades (min {self.min_trades})."
                if trades_passed
                else f"Insufficient trades executed ({trades} < {self.min_trades}).",
                value=trades,
                threshold=self.min_trades,
            )
        )

        # 2. Maximum drawdown check
        dd_passed = max_dd <= self.max_drawdown_pct
        checks.append(
            GateCheckItem(
                name="maximum_drawdown_limit",
                status=GateCheckStatus.PASSED if dd_passed else GateCheckStatus.FAILED,
                message=f"Max drawdown {max_dd:.2f}% within {self.max_drawdown_pct:.1f}% limit."
                if dd_passed
                else f"Max drawdown {max_dd:.2f}% exceeds limit of {self.max_drawdown_pct:.1f}%.",
                value=max_dd,
                threshold=self.max_drawdown_pct,
            )
        )

        # 3. Return vs Main baseline
        return_passed = return_diff >= 0.0
        checks.append(
            GateCheckItem(
                name="return_vs_baseline",
                status=GateCheckStatus.PASSED if return_passed else GateCheckStatus.FAILED,
                message=f"Net return delta vs baseline is {return_diff:+.2f}%."
                if return_passed
                else f"Candidate underperformed baseline by {abs(return_diff):.2f}%.",
                value=return_diff,
                threshold=0.0,
            )
        )

        # 4. Zero runtime errors
        errors_passed = runtime_errors == 0
        checks.append(
            GateCheckItem(
                name="runtime_stability",
                status=GateCheckStatus.PASSED if errors_passed else GateCheckStatus.FAILED,
                message="Zero runtime errors or balance discrepancies."
                if errors_passed
                else f"Encountered {runtime_errors} runtime error(s) during simulation.",
                value=runtime_errors,
                threshold=0,
            )
        )

        if not trades_passed:
            decision = GateDecision.INCONCLUSIVE
        elif dd_passed and return_passed and errors_passed:
            decision = GateDecision.PASS
        else:
            decision = GateDecision.FAIL

        return GateEvaluationResult(
            gate_name="Gate B: Simulation to Promotion Eligibility",
            decision=decision,
            checks=checks,
            evaluated_at=datetime.now(timezone.utc),
        )

    def evaluate_gate_c(
            self,
            approver: str,
            merge_preview: dict[str, Any],
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        has_approver = bool(approver and approver.strip())
        checks.append(
            GateCheckItem(
                name="authorized_approver",
                status=GateCheckStatus.PASSED if has_approver else GateCheckStatus.FAILED,
                message=f"Approved by operator: {approver.strip()}."
                if has_approver
                else "Operator signature / identity is missing.",
                value=approver,
            )
        )

        conflicts = merge_preview.get("conflicts", [])
        no_conflicts = len(conflicts) == 0
        checks.append(
            GateCheckItem(
                name="merge_conflict_free",
                status=GateCheckStatus.PASSED if no_conflicts else GateCheckStatus.FAILED,
                message="No merge conflicts against main HEAD."
                if no_conflicts
                else f"Found {len(conflicts)} conflict(s) with current main.",
                value=len(conflicts),
                threshold=0,
            )
        )

        all_passed = all(c.status == GateCheckStatus.PASSED for c in checks)
        decision = GateDecision.PASS if all_passed else GateDecision.FAIL

        return GateEvaluationResult(
            gate_name="Gate C: Promotion to Main",
            decision=decision,
            checks=checks,
            evaluated_at=datetime.now(timezone.utc),
        )
