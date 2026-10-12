from __future__ import annotations

from typing import Sequence

from api.interfaces.walk_forward import FoldMetricsSummary, WalkForwardSummary


class WalkForwardAggregator:
    @staticmethod
    def _calculate_drawdowns(fold_metrics: Sequence[FoldMetricsSummary]) -> tuple[float, float]:
        cumulative_mult = 1.0
        peak = 1.0
        max_dd = 0.0

        for f in fold_metrics:
            r = f.test_return_pct / 100.0
            cumulative_mult *= (1.0 + r)
            peak = max(peak, cumulative_mult)
            dd = (peak - cumulative_mult) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        oos_return = round((cumulative_mult - 1.0) * 100.0, 2)
        oos_drawdown = round(max_dd * 100.0, 2)
        return oos_return, oos_drawdown

    @staticmethod
    def _determine_verdict(ratio: float, oos_ret: float, wfe: float) -> tuple[str, str]:
        if ratio >= 0.6 and oos_ret > 0 and wfe >= 0.5:
            return (
                "ROBUST",
                "ROBUST: Strategy demonstrates consistent out-of-sample edge across evaluation folds.",
            )
        if oos_ret > 0:
            return (
                "UNSTABLE",
                "UNSTABLE: Aggregate return is positive but driven by minority of folds; high regime sensitivity.",
            )
        return (
            "DETERIORATING",
            "DETERIORATING: Strategy fails to generalize out-of-sample or exhibits severe degradation.",
        )

    @staticmethod
    def _populate_compatibility_fields(fold_metrics: Sequence[FoldMetricsSummary]) -> None:
        for f in fold_metrics:
            if f.out_of_sample_trades is None:
                f.out_of_sample_trades = f.test_trades_count
            if f.out_of_sample_win_rate_pct is None:
                f.out_of_sample_win_rate_pct = f.test_win_rate_pct
            if f.out_of_sample_profit_factor is None:
                f.out_of_sample_profit_factor = f.test_profit_factor
            if f.in_sample_trades is None:
                f.in_sample_trades = 0

    @classmethod
    def aggregate(
            cls,
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

        aggregate_oos_return_pct, max_oos_drawdown_pct = cls._calculate_drawdowns(fold_metrics)

        avg_is = sum(f.train_return_pct for f in fold_metrics) / total
        avg_oos = sum(f.test_return_pct for f in fold_metrics) / total
        if avg_is > 0:
            wfe = round(avg_oos / avg_is, 2)
        elif avg_is == 0 and avg_oos > 0:
            wfe = 1.0
        else:
            wfe = 0.0

        classification, verdict = cls._determine_verdict(ratio, aggregate_oos_return_pct, wfe)
        cls._populate_compatibility_fields(fold_metrics)

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
            out_of_sample_return_pct=aggregate_oos_return_pct,
            max_out_of_sample_drawdown_pct=max_oos_drawdown_pct,
            walk_forward_efficiency_ratio=wfe,
            stability_classification=classification,
            folds=list(fold_metrics),
            in_sample_return_pct=round(avg_is, 2),
        )
