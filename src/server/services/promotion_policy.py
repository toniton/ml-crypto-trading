from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from api.interfaces.promotion import (
    GateCheckItem,
    GateCheckStatus,
    GateDecision,
    GateEvaluationResult,
)
from src.server.services.canonical_config import CanonicalConfigService


class PromotionPolicy:
    def __init__(
            self,
            min_trades: int = 5,
            max_drawdown_pct: float = 15.0,
            require_prior_backtest: bool = True,
            authorized_approvers: Optional[set[str]] = None,
    ) -> None:
        self.min_trades = min_trades
        self.max_drawdown_pct = max_drawdown_pct
        self.require_prior_backtest = require_prior_backtest
        self.authorized_approvers = authorized_approvers

    def evaluate_gate_a(
            self,
            candidate: dict[str, Any],
            experiment: dict[str, Any],
            base_commit: Optional[str] = None,
            run_bindings: Optional[list[dict[str, Any]]] = None,
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        # 1. Configuration schema check
        weights = candidate.get("strategy_weights") or {}
        strategies = candidate.get("strategies") or []
        has_weights = isinstance(weights, dict) and len(weights) > 0
        has_strategies = isinstance(strategies, list) and len(strategies) > 0
        has_config = has_weights or has_strategies
        checks.append(
            GateCheckItem(
                name="configuration_valid",
                status=GateCheckStatus.PASSED if has_config else GateCheckStatus.FAILED,
                message="Candidate contains valid strategy configuration."
                if has_config
                else "Candidate strategy configuration is missing or empty.",
                value=len(weights) if weights else len(strategies),
            )
        )

        # 2. Source commit traceability (reject "HEAD" or invalid hashes)
        source_commit = candidate.get("candidate_commit_hash") or base_commit or experiment.get("base_commit_hash")
        valid_commit = CanonicalConfigService.validate_commit_hash(source_commit)
        checks.append(
            GateCheckItem(
                name="source_commit_traceable",
                status=GateCheckStatus.PASSED if valid_commit else GateCheckStatus.FAILED,
                message=f"Tied to immutable source commit {str(source_commit)[:8]}."
                if valid_commit
                else f"Source commit '{source_commit}' is invalid, uncommitted, or unpinned HEAD.",
                value=source_commit,
            )
        )

        # 3. Prior backtest verification
        bindings = run_bindings or experiment.get("run_bindings", [])
        has_backtest = bool(bindings and len(bindings) > 0)
        backtest_passed = has_backtest or not self.require_prior_backtest
        checks.append(
            GateCheckItem(
                name="prior_backtest_exists",
                status=GateCheckStatus.PASSED if backtest_passed else GateCheckStatus.FAILED,
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
            operational_diagnostics: Optional[dict[str, Any]] = None,
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        trades = int(metrics.get("executed_trades", 0))
        max_dd = float(metrics.get("max_drawdown_pct", 0.0))
        net_return = float(metrics.get("net_return_pct", 0.0))

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

        # 3. Return vs Baseline check (Mandatory baseline requirement)
        if baseline_metrics is not None and "net_return_pct" in baseline_metrics:
            baseline_return = float(baseline_metrics["net_return_pct"])
            return_diff = net_return - baseline_return
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
        else:
            return_passed = False
            checks.append(
                GateCheckItem(
                    name="return_vs_baseline",
                    status=GateCheckStatus.FAILED,
                    message="Mandatory baseline comparison metrics are missing.",
                    value=None,
                    threshold=0.0,
                )
            )

        # 4. Operational Stability & Diagnostic Telemetry
        has_diagnostics = (
            operational_diagnostics is not None
            and operational_diagnostics.get("telemetry_available") is True
        )
        runtime_errors = int((operational_diagnostics or {}).get("runtime_errors_count", 0))
        errors_passed = has_diagnostics and runtime_errors == 0
        if errors_passed:
            stability_msg = "Zero runtime errors verified by active telemetry."
        elif not has_diagnostics:
            stability_msg = "Diagnostic telemetry missing or unavailable."
        else:
            stability_msg = f"Encountered {runtime_errors} runtime error(s)."

        checks.append(
            GateCheckItem(
                name="runtime_stability",
                status=GateCheckStatus.PASSED if errors_passed else GateCheckStatus.FAILED,
                message=stability_msg,
                value=runtime_errors if has_diagnostics else None,
                threshold=0,
            )
        )

        if not trades_passed or baseline_metrics is None or not has_diagnostics:
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
            config_hash_match: bool = True,
    ) -> GateEvaluationResult:
        checks: list[GateCheckItem] = []

        clean_approver = (approver or "").strip()
        invalid_approvers = {"anonymous", "unknown", "none"}
        is_known = len(clean_approver) >= 3 and clean_approver.lower() not in invalid_approvers
        if self.authorized_approvers is not None:
            is_authorized = clean_approver in self.authorized_approvers
        else:
            is_authorized = is_known

        checks.append(
            GateCheckItem(
                name="authorized_approver",
                status=GateCheckStatus.PASSED if is_authorized else GateCheckStatus.FAILED,
                message=f"Authorized operator approval verified: {clean_approver}."
                if is_authorized
                else f"Operator '{clean_approver}' is not authorized to promote to main.",
                value=clean_approver,
            )
        )

        checks.append(
            GateCheckItem(
                name="evidence_hash_match",
                status=GateCheckStatus.PASSED if config_hash_match else GateCheckStatus.FAILED,
                message="Simulation report config hash matches candidate canonical snapshot."
                if config_hash_match
                else "Candidate configuration was modified after simulation report was generated.",
                value=config_hash_match,
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
