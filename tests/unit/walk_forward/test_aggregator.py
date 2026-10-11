from __future__ import annotations

from api.interfaces.walk_forward import FoldMetricsSummary
from src.walk_forward.analysis.aggregator import WalkForwardAggregator


def _make_fold_metric(idx: int, train_r: float, test_r: float, dd: float = 3.0) -> FoldMetricsSummary:
    return FoldMetricsSummary(
        fold_index=idx,
        train_return_pct=train_r,
        test_return_pct=test_r,
        test_max_drawdown_pct=dd,
        test_trades_count=10,
        test_win_rate_pct=60.0,
        test_profit_factor=1.8,
    )


class TestWalkForwardAggregator:
    def test_handles_empty_folds(self):
        summary = WalkForwardAggregator.aggregate("wf_1", "BTC_USD", [])
        assert summary.total_folds == 0
        assert summary.profitable_folds == 0
        assert summary.aggregate_oos_return_pct == 0.0
        assert summary.verdict == "NO_FOLDS_EVALUATED"

    def test_aggregates_robust_folds(self):
        folds = [
            _make_fold_metric(0, train_r=10.0, test_r=6.0),
            _make_fold_metric(1, train_r=12.0, test_r=7.0),
            _make_fold_metric(2, train_r=8.0, test_r=5.0),
            _make_fold_metric(3, train_r=15.0, test_r=8.0),
            _make_fold_metric(4, train_r=11.0, test_r=6.0),
        ]
        summary = WalkForwardAggregator.aggregate("wf_2", "BTC_USD", folds)
        assert summary.total_folds == 5
        assert summary.profitable_folds == 5
        assert summary.profitable_fold_ratio == 1.0
        assert summary.aggregate_oos_return_pct > 0.0
        assert summary.walk_forward_efficiency >= 0.5
        assert "ROBUST" in summary.verdict

    def test_detects_deteriorating_folds(self):
        folds = [
            _make_fold_metric(0, train_r=10.0, test_r=-2.0),
            _make_fold_metric(1, train_r=12.0, test_r=-4.0),
            _make_fold_metric(2, train_r=15.0, test_r=-1.0),
        ]
        summary = WalkForwardAggregator.aggregate("wf_3", "BTC_USD", folds)
        assert summary.profitable_folds == 0
        assert summary.aggregate_oos_return_pct < 0.0
        assert "DETERIORATING" in summary.verdict

    def test_detects_unstable_folds(self):
        folds = [
            _make_fold_metric(0, train_r=10.0, test_r=25.0),
            _make_fold_metric(1, train_r=12.0, test_r=-3.0),
            _make_fold_metric(2, train_r=15.0, test_r=-4.0),
            _make_fold_metric(3, train_r=8.0, test_r=-2.0),
        ]
        summary = WalkForwardAggregator.aggregate("wf_4", "BTC_USD", folds)
        assert summary.aggregate_oos_return_pct > 0.0
        assert summary.profitable_fold_ratio == 0.25
        assert "UNSTABLE" in summary.verdict
