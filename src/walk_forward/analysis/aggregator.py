from __future__ import annotations

from typing import Sequence

from api.interfaces.walk_forward import FoldMetricsSummary, WalkForwardSummary


class WalkForwardAggregator:
    @staticmethod
    def aggregate(
            run_id: str,
            ticker_symbol: str,
            fold_metrics: Sequence[FoldMetricsSummary],
    ) -> WalkForwardSummary:
        total = len(fold_metrics)
        if total == 0:
            return WalkForwardSummary(
                run_id=run_id,
                ticker_symbol=ticker_symbol,
                total_folds=0,
                profitable_folds=0,
                profitable_fold_ratio=0.0,
                aggregate_oos_return_pct=0.0,
                max_oos_drawdown_pct=0.0,
                walk_forward_efficiency=0.0,
                fold_results=[],
                verdict="NO_FOLDS_EVALUATED",
            )

        profitable = sum(1 for f in fold_metrics if f.test_return_pct > 0.0)
        ratio = round(profitable / total, 3)

        # Compounded cumulative out-of-sample growth
        cumulative_mult = 1.0
        peak = 1.0
        max_dd = 0.0

        for f in fold_metrics:
            r = f.test_return_pct / 100.0
            cumulative_mult *= (1.0 + r)
            if cumulative_mult > peak:
                peak = cumulative_mult
            dd = (peak - cumulative_mult) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        aggregate_oos_return_pct = round((cumulative_mult - 1.0) * 100.0, 2)
        max_oos_drawdown_pct = round(max_dd * 100.0, 2)

        # Walk-Forward Efficiency (WFE): Avg(OOS) / Avg(IS)
        avg_is = sum(f.train_return_pct for f in fold_metrics) / total
        avg_oos = sum(f.test_return_pct for f in fold_metrics) / total
        if avg_is > 0:
            wfe = round(avg_oos / avg_is, 2)
        elif avg_is == 0 and avg_oos > 0:
            wfe = 1.0
        else:
            wfe = 0.0

        if ratio >= 0.6 and aggregate_oos_return_pct > 0 and wfe >= 0.5:
            verdict = "ROBUST: Strategy demonstrates consistent out-of-sample edge across evaluation folds."
        elif aggregate_oos_return_pct > 0:
            verdict = "UNSTABLE: Aggregate return is positive but driven by minority of folds; high regime sensitivity."
        else:
            verdict = "DETERIORATING: Strategy fails to generalize out-of-sample or exhibits severe degradation."

        return WalkForwardSummary(
            run_id=run_id,
            ticker_symbol=ticker_symbol,
            total_folds=total,
            profitable_folds=profitable,
            profitable_fold_ratio=ratio,
            aggregate_oos_return_pct=aggregate_oos_return_pct,
            max_oos_drawdown_pct=max_oos_drawdown_pct,
            walk_forward_efficiency=wfe,
            fold_results=list(fold_metrics),
            verdict=verdict,
        )
