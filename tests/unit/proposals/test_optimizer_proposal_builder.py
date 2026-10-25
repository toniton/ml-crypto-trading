from __future__ import annotations

from decimal import Decimal

from src.proposals.optimizer_proposal_builder import OptimizerProposalBuilder
from src.trading.analytics.strategy_optimizer import (
    BaselineComparisonMetrics,
    BaselineComparisonResult,
)


class TestOptimizerProposalBuilderMetrics:
    def _create_sample_baseline_eval(self) -> BaselineComparisonResult:
        base_m = BaselineComparisonMetrics(
            net_pnl=Decimal("120.50"),
            gross_wins=Decimal("200.00"),
            gross_losses=Decimal("79.50"),
            profit_factor=2.51,
            win_rate_pct=65.0,
            trades_count=20,
        )
        prop_m = BaselineComparisonMetrics(
            net_pnl=Decimal("250.75"),
            gross_wins=Decimal("310.00"),
            gross_losses=Decimal("59.25"),
            profit_factor=5.23,
            win_rate_pct=75.0,
            trades_count=22,
        )
        return BaselineComparisonResult(
            baseline_metrics=base_m,
            proposed_metrics=prop_m,
            equal_weight_metrics=base_m,
            pnl_delta=Decimal("130.25"),
            pnl_improvement_pct=108.09,
            in_sample_trades_count=15,
            out_of_sample_trades_count=7,
            demonstrates_improvement=True,
            verdict="Improved",
        )

    def test_expected_benefit_stores_currency_in_net_pnl(self):
        baseline_eval = self._create_sample_baseline_eval()
        benefit = OptimizerProposalBuilder._build_expected_benefit(baseline_eval)  # pylint: disable=protected-access

        assert benefit.net_pnl is not None
        assert benefit.net_pnl.baseline_value == 120.50
        assert benefit.net_pnl.candidate_value == 250.75
        assert benefit.net_pnl.absolute_delta == 130.25

    def test_expected_benefit_does_not_populate_net_return_pct_with_dollar_amount(self):
        baseline_eval = self._create_sample_baseline_eval()
        benefit = OptimizerProposalBuilder._build_expected_benefit(baseline_eval)  # pylint: disable=protected-access

        assert benefit.net_return_pct.candidate_value is None

    def test_expected_benefit_does_not_populate_out_of_sample_return_pct_with_dollar_amount(self):
        baseline_eval = self._create_sample_baseline_eval()
        benefit = OptimizerProposalBuilder._build_expected_benefit(baseline_eval)  # pylint: disable=protected-access

        assert benefit.out_of_sample_return_pct is None
