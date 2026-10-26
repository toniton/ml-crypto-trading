from __future__ import annotations

from api.interfaces.promotion import GateCheckStatus, GateDecision
from src.server.services.promotion_policy import PromotionPolicy


class TestPromotionPolicy:
    def setup_method(self):
        self.policy = PromotionPolicy(min_trades=5, max_drawdown_pct=15.0)

    def test_gate_a_passes_with_valid_candidate_and_commit(self):
        candidate = {
            "candidate_id": "cand_1",
            "strategy_weights": {"TrendFollowing": 1.2, "RsiOversold": 0.8},
            "candidate_commit_hash": "commit_123456",
        }
        experiment = {
            "base_commit_hash": "base_commit_111",
            "run_bindings": [{"run_id": "bt_01"}],
        }

        result = self.policy.evaluate_gate_a(candidate, experiment)
        assert result.decision == GateDecision.PASS
        assert all(c.status == GateCheckStatus.PASSED for c in result.checks)

    def test_gate_a_fails_when_weights_are_empty(self):
        candidate = {
            "candidate_id": "cand_empty",
            "strategy_weights": {},
            "candidate_commit_hash": "commit_123456",
        }
        experiment = {
            "base_commit_hash": "base_commit_111",
            "run_bindings": [{"run_id": "bt_01"}],
        }

        result = self.policy.evaluate_gate_a(candidate, experiment)
        assert result.decision == GateDecision.FAIL
        failed_check = next(c for c in result.checks if c.name == "configuration_valid")
        assert failed_check.status == GateCheckStatus.FAILED

    def test_gate_b_passes_with_sufficient_trades_and_controlled_drawdown(self):
        metrics = {
            "executed_trades": 8,
            "max_drawdown_pct": 6.5,
            "net_return_pct": 4.2,
            "runtime_errors_count": 0,
        }
        baseline = {"net_return_pct": 2.0}

        result = self.policy.evaluate_gate_b(metrics, baseline)
        assert result.decision == GateDecision.PASS

    def test_gate_b_inconclusive_when_trades_below_minimum(self):
        metrics = {
            "executed_trades": 3,
            "max_drawdown_pct": 4.0,
            "net_return_pct": 10.0,
            "runtime_errors_count": 0,
        }

        result = self.policy.evaluate_gate_b(metrics)
        assert result.decision == GateDecision.INCONCLUSIVE
        check = next(c for c in result.checks if c.name == "minimum_executed_trades")
        assert check.status == GateCheckStatus.FAILED

    def test_gate_b_fails_when_drawdown_exceeds_limit(self):
        metrics = {
            "executed_trades": 10,
            "max_drawdown_pct": 18.5,
            "net_return_pct": 12.0,
            "runtime_errors_count": 0,
        }

        result = self.policy.evaluate_gate_b(metrics)
        assert result.decision == GateDecision.FAIL
        check = next(c for c in result.checks if c.name == "maximum_drawdown_limit")
        assert check.status == GateCheckStatus.FAILED

    def test_gate_b_fails_when_candidate_underperforms_baseline(self):
        metrics = {
            "executed_trades": 10,
            "max_drawdown_pct": 5.0,
            "net_return_pct": -2.0,
            "runtime_errors_count": 0,
        }
        baseline = {"net_return_pct": 3.0}

        result = self.policy.evaluate_gate_b(metrics, baseline)
        assert result.decision == GateDecision.FAIL
        check = next(c for c in result.checks if c.name == "return_vs_baseline")
        assert check.status == GateCheckStatus.FAILED

    def test_gate_b_fails_when_runtime_errors_occur(self):
        metrics = {
            "executed_trades": 10,
            "max_drawdown_pct": 5.0,
            "net_return_pct": 8.0,
            "runtime_errors_count": 2,
        }

        result = self.policy.evaluate_gate_b(metrics)
        assert result.decision == GateDecision.FAIL
        check = next(c for c in result.checks if c.name == "runtime_stability")
        assert check.status == GateCheckStatus.FAILED

    def test_gate_c_passes_with_approver_and_no_conflicts(self):
        preview = {"conflicts": [], "can_fast_forward": True}
        result = self.policy.evaluate_gate_c("operator_alice", preview)
        assert result.decision == GateDecision.PASS

    def test_gate_c_fails_with_missing_approver(self):
        preview = {"conflicts": []}
        result = self.policy.evaluate_gate_c("", preview)
        assert result.decision == GateDecision.FAIL
        check = next(c for c in result.checks if c.name == "authorized_approver")
        assert check.status == GateCheckStatus.FAILED

    def test_gate_c_fails_with_merge_conflicts(self):
        preview = {"conflicts": [{"path": "assets.BTC_USD.strategies"}]}
        result = self.policy.evaluate_gate_c("operator_alice", preview)
        assert result.decision == GateDecision.FAIL
        check = next(c for c in result.checks if c.name == "merge_conflict_free")
        assert check.status == GateCheckStatus.FAILED
