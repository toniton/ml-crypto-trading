from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from api.interfaces.trade import Trade
from src.core.weekday import Weekday
from src.trading.analytics.trade_attribution_service import TradeAttributionService
from src.trading.strategies.models.strategy_schedule import TradingWindow
from src.vcs.domain.diff import ConfigChange, ConfigurationProposal


@dataclass(frozen=True)
class HourlyProfitabilityProfile:
    weekday: Weekday
    hour: int
    total_trades: int
    winning_trades: int
    win_rate_pct: float
    net_pnl: Decimal
    gross_pnl: Decimal
    profit_factor: float


@dataclass(frozen=True)
class StrategyCalibrationRecommendation:
    strategy_name: str
    current_weight: float
    recommended_weight: float
    profit_factor: float
    win_rate_pct: float
    total_trades: int
    rationale: str
    confidence_level: str = "LOW"
    sample_margin_of_error_pct: float = 0.0


@dataclass(frozen=True)
class BaselineComparisonMetrics:
    net_pnl: Decimal
    gross_wins: Decimal
    gross_losses: Decimal
    profit_factor: float
    win_rate_pct: float
    trades_count: int


@dataclass(frozen=True)
class BaselineComparisonResult:
    baseline_metrics: BaselineComparisonMetrics
    proposed_metrics: BaselineComparisonMetrics
    equal_weight_metrics: BaselineComparisonMetrics
    pnl_delta: Decimal
    pnl_improvement_pct: float
    in_sample_trades_count: int
    out_of_sample_trades_count: int
    demonstrates_improvement: bool
    verdict: str


@dataclass(frozen=True)
class StrategyRedundancyRecommendation:
    strategy_a: str
    strategy_b: str
    agreement_rate_pct: float
    co_sponsored_trades: int
    recommendation: str
    aligned_decisions: int = 0


class StrategyOptimizer:
    """Provides empirical calibration for strategy weights, trading windows, and redundancy management."""

    @classmethod
    def _compute_baseline_scores(
            cls,
            current_weights: dict[str, float],
            attr_metrics: dict[str, Any],
    ) -> tuple[dict[str, float], float]:
        scores: dict[str, float] = {}
        for name in current_weights:
            metrics = attr_metrics.get(name)
            if not metrics or metrics.total_trades == 0:
                scores[name] = 1.0
                continue
            win_rate_score = max(0.2, metrics.win_rate_pct / 50.0)
            pf = min(5.0, metrics.profit_factor) if metrics.profit_factor > 0 else 0.5
            scores[name] = round(win_rate_score * (pf ** 0.5), 3)

        avg_score = sum(scores.values()) / len(scores) if scores else 1.0
        return scores, avg_score

    @staticmethod
    def _calculate_sample_uncertainty(total_trades: int, win_rate_pct: float) -> tuple[str, float]:
        if total_trades <= 0:
            return "LOW", 0.0
        p = win_rate_pct / 100.0
        variance = max(0.0, p * (1.0 - p))
        margin_of_error = round(1.96 * ((variance / total_trades) ** 0.5) * 100.0, 1)
        if total_trades < 5:
            confidence = "LOW"
        elif total_trades < 20:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"
        return confidence, margin_of_error

    @staticmethod
    def _calculate_adjusted_weight(
            current_w: float,
            score: float,
            avg_score: float,
            total_trades: int,
            min_weight: float,
            max_weight: float,
    ) -> float:
        if total_trades < 3:
            return current_w
        ratio = score / avg_score if avg_score > 0 else 1.0
        if total_trades < 10:
            shrinkage = total_trades / 10.0
            effective_ratio = 1.0 + (ratio - 1.0) * shrinkage
        else:
            effective_ratio = ratio
        return max(min_weight, min(max_weight, round(current_w * effective_ratio, 2)))

    @staticmethod
    def _format_calibration_rationale(
            current_w: float,
            rec_weight: float,
            wr: float,
            moe: float,
            pf: float,
            confidence: str,
            total_trades: int,
    ) -> str:
        if total_trades < 3:
            return (
                f"Insufficient sample size ({total_trades} trades); maintaining weight at {current_w:.2f} "
                f"(Confidence: {confidence})."
            )
        prefix = f"(Win Rate: {wr:.1f}% ± {moe:.1f}%, PF: {pf:.2f}, Confidence: {confidence})"
        if rec_weight > current_w:
            delta = rec_weight - current_w
            return f"Strong performance {prefix}; recommended increase by +{delta:.2f} to {rec_weight:.2f}."
        if rec_weight < current_w:
            delta = current_w - rec_weight
            return f"Subpar performance {prefix}; recommended reduction by -{delta:.2f} to {rec_weight:.2f}."
        return f"Balanced performance {prefix}; optimal weight is {current_w:.2f}."

    @classmethod
    def _create_calibration_recommendation(
            cls,
            name: str,
            current_w: float,
            score: float,
            avg_score: float,
            metrics: Any,
            min_weight: float,
            max_weight: float,
    ) -> StrategyCalibrationRecommendation:
        total_trades = metrics.total_trades if metrics else 0
        pf = metrics.profit_factor if metrics else 0.0
        wr = metrics.win_rate_pct if metrics else 0.0

        confidence, moe = cls._calculate_sample_uncertainty(total_trades, wr)
        rec_weight = cls._calculate_adjusted_weight(
            current_w, score, avg_score, total_trades, min_weight, max_weight
        )
        rationale = cls._format_calibration_rationale(
            current_w, rec_weight, wr, moe, pf, confidence, total_trades
        )

        return StrategyCalibrationRecommendation(
            strategy_name=name,
            current_weight=current_w,
            recommended_weight=rec_weight,
            profit_factor=pf,
            win_rate_pct=wr,
            total_trades=total_trades,
            rationale=rationale,
            confidence_level=confidence,
            sample_margin_of_error_pct=moe,
        )

    @classmethod
    def calibrate_strategy_weights(
            cls,
            trades: list[Trade],
            current_weights: dict[str, float],
            min_weight: float = 0.1,
            max_weight: float = 2.0,
    ) -> list[StrategyCalibrationRecommendation]:
        if not trades or not current_weights:
            return []

        attr_metrics = TradeAttributionService.attribute_by_strategy_proportional(trades)
        scores, avg_score = cls._compute_baseline_scores(current_weights, attr_metrics)

        return [
            cls._create_calibration_recommendation(
                name=name,
                current_w=current_w,
                score=scores.get(name, 1.0),
                avg_score=avg_score,
                metrics=attr_metrics.get(name),
                min_weight=min_weight,
                max_weight=max_weight,
            )
            for name, current_w in current_weights.items()
        ]

    @classmethod
    def profile_hourly_profitability(
            cls,
            trades: list[Trade],
            timezone_str: str = "UTC",
    ) -> list[HourlyProfitabilityProfile]:
        tz = ZoneInfo(timezone_str)
        hourly_buckets: dict[tuple[int, int], list[Trade]] = defaultdict(list)

        for trade in trades:
            dt = datetime.fromtimestamp(trade.entry_timestamp, tz=timezone.utc).astimezone(tz)
            weekday = dt.weekday()
            hour = dt.hour
            hourly_buckets[(weekday, hour)].append(trade)

        profiles: list[HourlyProfitabilityProfile] = []
        for (weekday_idx, hour), bucket in sorted(hourly_buckets.items()):
            metrics = TradeAttributionService.calculate_metrics(bucket)
            profiles.append(
                HourlyProfitabilityProfile(
                    weekday=Weekday(weekday_idx),
                    hour=hour,
                    total_trades=metrics.total_trades,
                    winning_trades=metrics.winning_trades,
                    win_rate_pct=metrics.win_rate_pct,
                    net_pnl=metrics.net_pnl,
                    gross_pnl=metrics.gross_pnl,
                    profit_factor=metrics.profit_factor,
                )
            )

        return profiles

    @classmethod
    def _extract_contiguous_day_ranges(
            cls,
            profitable_slots: dict[Weekday, set[int]],
    ) -> dict[Weekday, list[tuple[int, int]]]:
        day_ranges: dict[Weekday, list[tuple[int, int]]] = {}
        for weekday, hours in sorted(profitable_slots.items(), key=lambda x: x[0].value):
            sorted_hours = sorted(hours)
            if not sorted_hours:
                continue

            ranges: list[tuple[int, int]] = []
            start_h = sorted_hours[0]
            prev_h = start_h
            for h in sorted_hours[1:]:
                if h == prev_h + 1:
                    prev_h = h
                else:
                    ranges.append((start_h, prev_h + 1))
                    start_h = h
                    prev_h = h
            ranges.append((start_h, prev_h + 1))
            day_ranges[weekday] = ranges
        return day_ranges

    @classmethod
    def _build_trading_windows_from_ranges(
            cls,
            day_ranges: dict[Weekday, list[tuple[int, int]]],
    ) -> list[TradingWindow]:
        range_to_days: dict[tuple[int, int], list[Weekday]] = defaultdict(list)
        for weekday, ranges in day_ranges.items():
            for r in ranges:
                range_to_days[r].append(weekday)

        windows: list[TradingWindow] = []
        for (start_h, end_h), days in sorted(range_to_days.items(), key=lambda x: (x[0][0], x[0][1])):
            start_t = time(hour=start_h, minute=0, second=0)
            end_t = time(hour=23, minute=59, second=59) if end_h >= 24 else time(hour=end_h, minute=0, second=0)
            windows.append(
                TradingWindow(
                    days=days,
                    start_time=start_t,
                    end_time=end_t,
                )
            )
        return windows

    @classmethod
    def optimize_trading_windows(
            cls,
            trades: list[Trade],
            timezone_str: str = "UTC",
            min_trades: int = 2,
            min_win_rate: float = 50.0,
    ) -> list[TradingWindow]:
        profiles = cls.profile_hourly_profitability(trades, timezone_str=timezone_str)
        profitable_slots: dict[Weekday, set[int]] = defaultdict(set)

        for p in profiles:
            if p.total_trades >= min_trades and p.win_rate_pct >= min_win_rate and p.net_pnl > Decimal(0):
                profitable_slots[p.weekday].add(p.hour)

        if not profitable_slots:
            return []

        day_ranges = cls._extract_contiguous_day_ranges(profitable_slots)
        return cls._build_trading_windows_from_ranges(day_ranges)

    @classmethod
    def optimize_strategy_trading_windows(
            cls,
            trades: list[Trade],
            strategy_name: str,
            timezone_str: str = "UTC",
            min_trades: int = 2,
            min_win_rate: float = 50.0,
    ) -> list[TradingWindow]:
        strategy_trades = [
            t for t in trades
            if (t.entry_strategy_attributions and strategy_name in t.entry_strategy_attributions)
               or t.winning_strategy == strategy_name
        ]
        if not strategy_trades:
            return []
        return cls.optimize_trading_windows(
            strategy_trades,
            timezone_str=timezone_str,
            min_trades=min_trades,
            min_win_rate=min_win_rate,
        )

    @classmethod
    def _evaluate_pair_redundancy(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            s1: str,
            s2: str,
            trades: list[Trade],
            matrix: dict[str, dict[str, float]],
            counts: dict[str, dict[str, int]],
            threshold: float,
            min_sample: int,
    ) -> Optional[StrategyRedundancyRecommendation]:
        aligned_n = counts.get(s1, {}).get(s2, 0)
        if aligned_n < min_sample:
            return None

        rate_1 = matrix.get(s1, {}).get(s2, 0.0)
        rate_2 = matrix.get(s2, {}).get(s1, 0.0)
        avg_rate = (rate_1 + rate_2) / 2.0

        if avg_rate < threshold:
            return None

        pct = round(avg_rate * 100.0, 1)
        rec = (
            f"Observed high co-voting alignment ({pct}% agreement over {aligned_n} aligned decisions). "
            f"Investigate signal overlap and regime specialization before making allocation changes."
        )
        co_trades = sum(
            1 for t in trades
            if t.entry_strategy_attributions
            and s1 in t.entry_strategy_attributions
            and s2 in t.entry_strategy_attributions
        )
        return StrategyRedundancyRecommendation(
            strategy_a=s1,
            strategy_b=s2,
            agreement_rate_pct=pct,
            co_sponsored_trades=co_trades,
            recommendation=rec,
            aligned_decisions=aligned_n,
        )

    @classmethod
    def detect_strategy_redundancies(
            cls,
            trades: list[Trade],
            agreement_threshold: float = 0.85,
            min_sample_size: int = 2,
    ) -> list[StrategyRedundancyRecommendation]:
        matrix, counts = TradeAttributionService.compute_co_voting_details(trades)
        recommendations: list[StrategyRedundancyRecommendation] = []
        strategies = sorted(matrix.keys())

        for i, s1 in enumerate(strategies):
            for s2 in strategies[i + 1:]:
                rec = cls._evaluate_pair_redundancy(
                    s1, s2, trades, matrix, counts, agreement_threshold, min_sample_size
                )
                if rec is not None:
                    recommendations.append(rec)

        return recommendations

    @classmethod
    def _format_windows_payload(
            cls,
            windows: list[TradingWindow],
    ) -> list[dict[str, Any]]:
        return [
            {
                "days": [d.value for d in w.days],
                "start_time": w.start_time.strftime("%H:%M:%S"),
                "end_time": w.end_time.strftime("%H:%M:%S"),
            }
            for w in windows
        ]

    @classmethod
    def _build_strategy_schedule_change(
            cls,
            ticker_symbol: str,
            strat: dict[str, Any],
            suggested_windows: list[TradingWindow],
            trades: Optional[list[Trade]],
            timezone_str: str,
            allow_asset_fallback: bool,
    ) -> Optional[ConfigChange]:
        sname = strat.get("name")
        if not sname:
            return None

        strat_windows: list[TradingWindow] = []
        if trades:
            strat_windows = cls.optimize_strategy_trading_windows(
                trades,
                sname,
                timezone_str=timezone_str,
            )

        effective_windows = strat_windows if strat_windows else (suggested_windows if allow_asset_fallback else [])
        if not effective_windows:
            return None

        windows_payload = cls._format_windows_payload(effective_windows)
        sched = strat.get("schedule")
        current_windows = sched.get("windows", []) if isinstance(sched, dict) else []

        if windows_payload == current_windows:
            return None

        reason = (
            f"Empirically optimized active trading windows based on {sname}-specific trades."
            if strat_windows
            else f"Applied aggregate asset-level trading windows fallback for {sname}."
        )
        return ConfigChange(
            path=f"assets.{ticker_symbol}.strategies.{sname}.schedule.windows",
            old_value=current_windows,
            new_value=windows_payload,
            reason=reason,
        )

    @classmethod
    def _build_schedule_changes(
            cls,
            ticker_symbol: str,
            strategies_config: list[dict[str, Any]],
            suggested_windows: list[TradingWindow],
            trades: Optional[list[Trade]] = None,
            timezone_str: str = "UTC",
            allow_asset_fallback: bool = False,
    ) -> list[ConfigChange]:
        changes: list[ConfigChange] = []
        for strat in strategies_config:
            change = cls._build_strategy_schedule_change(
                ticker_symbol=ticker_symbol,
                strat=strat,
                suggested_windows=suggested_windows,
                trades=trades,
                timezone_str=timezone_str,
                allow_asset_fallback=allow_asset_fallback,
            )
            if change is not None:
                changes.append(change)
        return changes

    @staticmethod
    def _build_weight_changes(
            ticker_symbol: str,
            calibrations: list[StrategyCalibrationRecommendation],
    ) -> list[ConfigChange]:
        return [
            ConfigChange(
                path=f"assets.{ticker_symbol}.strategies.{cal.strategy_name}.weight",
                old_value=cal.current_weight,
                new_value=cal.recommended_weight,
                reason=cal.rationale,
            )
            for cal in calibrations
            if cal.recommended_weight != cal.current_weight
        ]

    @staticmethod
    def _build_proposal_narrative(
            ticker_symbol: str,
            calibrations: list[StrategyCalibrationRecommendation],
            windows: list[TradingWindow],
            baseline_eval: Optional[BaselineComparisonResult],
    ) -> tuple[str, list[str], str]:
        summary = (
            f"Autonomous calibration for {ticker_symbol}: "
            f"{len(calibrations)} strategy weight(s) evaluated and "
            f"{len(windows)} optimal trading window(s) discovered."
        )
        risks = [
            "Calibrated weights are empirical heuristics based on historical trade attribution.",
            "Narrowed trading windows will prevent signals during historically low-win-rate intervals.",
        ]
        if baseline_eval is not None and not baseline_eval.demonstrates_improvement:
            risks.append(
                f"Out-of-sample validation caution: {baseline_eval.verdict} "
                f"Review recommended before applying."
            )
        effect = (
            f"Aligns strategy influence with empirical risk-adjusted performance. "
            f"Out-of-sample walk-forward test: {baseline_eval.verdict}"
            if baseline_eval is not None
            else (
                "Aligns strategy influence with empirical risk-adjusted performance "
                "and restricts trading to high-probability windows."
            )
        )
        return summary, risks, effect

    @staticmethod
    def _extract_current_weights(strategies_config: list[dict[str, Any]]) -> dict[str, float]:
        return {
            strat.get("name", f"Strategy_{i}"): float(strat.get("weight", 1.0))
            for i, strat in enumerate(strategies_config)
            if strat.get("name")
        }

    @classmethod
    def _create_proposal(
            cls,
            ticker_symbol: str,
            calibrations: list[StrategyCalibrationRecommendation],
            windows: list[TradingWindow],
            changes: list[ConfigChange],
            baseline_eval: Optional[BaselineComparisonResult],
            base_commit_hash: Optional[str],
    ) -> ConfigurationProposal:
        summary, risks, effect = cls._build_proposal_narrative(
            ticker_symbol, calibrations, windows, baseline_eval
        )
        return ConfigurationProposal(
            summary=summary,
            changes=changes,
            risks=risks,
            expected_effect=effect,
            base_commit_hash=base_commit_hash,
        )

    @classmethod
    def generate_optimization_proposal(
            cls,
            ticker_symbol: str,
            current_asset_config: dict[str, Any],
            trades: list[Trade],
            timezone_str: str = "UTC",
            base_commit_hash: Optional[str] = None,
            allow_asset_fallback: bool = False,
    ) -> ConfigurationProposal:
        strategies_config = current_asset_config.get("strategies", [])
        current_weights = cls._extract_current_weights(strategies_config)

        calibrations = cls.calibrate_strategy_weights(trades, current_weights)
        suggested_windows = cls.optimize_trading_windows(trades, timezone_str=timezone_str)

        changes = cls._build_weight_changes(ticker_symbol, calibrations)
        changes.extend(
            cls._build_schedule_changes(
                ticker_symbol,
                strategies_config,
                suggested_windows,
                trades=trades,
                timezone_str=timezone_str,
                allow_asset_fallback=allow_asset_fallback,
            )
        )

        baseline_eval = cls.evaluate_split_sample_baseline(
            trades,
            current_weights,
            {cal.strategy_name: cal.recommended_weight for cal in calibrations},
        )

        return cls._create_proposal(
            ticker_symbol,
            calibrations,
            suggested_windows,
            changes,
            baseline_eval,
            base_commit_hash,
        )

    @staticmethod
    def _split_trades_chronologically(
            trades: list[Trade], train_ratio: float
    ) -> tuple[list[Trade], list[Trade]]:
        sorted_trades = sorted(trades, key=lambda t: t.exit_timestamp)
        split_idx = max(2, min(len(sorted_trades) - 1, int(len(sorted_trades) * train_ratio)))
        return sorted_trades[:split_idx], sorted_trades[split_idx:]

    @classmethod
    def _evaluate_out_of_sample_comparison(
            cls,
            out_of_sample: list[Trade],
            current_weights: dict[str, float],
            proposed_weights: dict[str, float],
            in_sample_count: int,
    ) -> BaselineComparisonResult:
        base_metrics = cls._simulate_weighted_performance(out_of_sample, current_weights)
        prop_metrics = cls._simulate_weighted_performance(out_of_sample, proposed_weights)
        equal_metrics = cls._simulate_weighted_performance(out_of_sample, {s: 1.0 for s in current_weights})

        pnl_delta = prop_metrics.net_pnl - base_metrics.net_pnl
        pnl_imp = cls._calculate_pnl_improvement(pnl_delta, base_metrics.net_pnl)
        improves = cls._check_demonstrates_improvement(prop_metrics, base_metrics)
        verdict = cls._build_baseline_verdict(improves, pnl_delta, pnl_imp, prop_metrics, base_metrics)

        return BaselineComparisonResult(
            baseline_metrics=base_metrics,
            proposed_metrics=prop_metrics,
            equal_weight_metrics=equal_metrics,
            pnl_delta=pnl_delta,
            pnl_improvement_pct=pnl_imp,
            in_sample_trades_count=in_sample_count,
            out_of_sample_trades_count=len(out_of_sample),
            demonstrates_improvement=improves,
            verdict=verdict,
        )

    @classmethod
    def evaluate_split_sample_baseline(
            cls,
            trades: list[Trade],
            current_weights: dict[str, float],
            proposed_weights: dict[str, float],
            train_ratio: float = 0.7,
    ) -> Optional[BaselineComparisonResult]:
        if not trades or not current_weights or not proposed_weights or len(trades) < 4:
            return None
        in_sample, out_of_sample = cls._split_trades_chronologically(trades, train_ratio)
        if not out_of_sample:
            return None
        return cls._evaluate_out_of_sample_comparison(
            out_of_sample, current_weights, proposed_weights, len(in_sample)
        )

    @classmethod
    def _simulate_weighted_performance(
            cls,
            trades: list[Trade],
            weights: dict[str, float],
    ) -> BaselineComparisonMetrics:
        if not trades:
            return BaselineComparisonMetrics(
                net_pnl=Decimal(0),
                gross_wins=Decimal(0),
                gross_losses=Decimal(0),
                profit_factor=0.0,
                win_rate_pct=0.0,
                trades_count=0,
            )

        total_w = sum(max(0.0, w) for w in weights.values())
        avg_w = (total_w / len(weights)) if weights and total_w > 0 else 1.0

        gross_wins = Decimal(0)
        gross_losses = Decimal(0)
        net_pnl = Decimal(0)
        winning_trades = 0

        for trade in trades:
            trade_net = cls._calculate_trade_weighted_net(trade, weights, avg_w)
            net_pnl += trade_net
            if trade_net > Decimal(0):
                gross_wins += trade_net
                winning_trades += 1
            elif trade_net < Decimal(0):
                gross_losses += abs(trade_net)

        profit_factor = cls._calculate_profit_factor(gross_wins, gross_losses)
        win_rate = round((winning_trades / len(trades) * 100.0), 2)

        return BaselineComparisonMetrics(
            net_pnl=net_pnl,
            gross_wins=gross_wins,
            gross_losses=gross_losses,
            profit_factor=profit_factor,
            win_rate_pct=win_rate,
            trades_count=len(trades),
        )

    @staticmethod
    def _calculate_trade_weighted_net(
            trade: Trade,
            weights: dict[str, float],
            avg_w: float,
    ) -> Decimal:
        attributions = trade.entry_strategy_attributions
        if not attributions:
            winning = trade.winning_strategy or "UNATTRIBUTED"
            attributions = {winning: 1.0}

        strat_mult = sum(
            float(weights.get(strat, 1.0)) * float(share)
            for strat, share in attributions.items()
        )
        norm_factor = strat_mult / avg_w if avg_w > 0 else 1.0
        norm_dec = Decimal(str(round(norm_factor, 6)))
        return trade.net_pnl * norm_dec

    @staticmethod
    def _calculate_profit_factor(gross_wins: Decimal, gross_losses: Decimal) -> float:
        if gross_losses > Decimal(0):
            return round(float(gross_wins / gross_losses), 2)
        if gross_wins > Decimal(0):
            return 999.99
        return 0.0

    @staticmethod
    def _calculate_pnl_improvement(pnl_delta: Decimal, base_net_pnl: Decimal) -> float:
        base_val = float(base_net_pnl)
        if abs(base_val) > 1e-6:
            return round((float(pnl_delta) / abs(base_val)) * 100.0, 2)
        return 100.0 if pnl_delta > Decimal(0) else 0.0

    @staticmethod
    def _check_demonstrates_improvement(
            prop: BaselineComparisonMetrics,
            base: BaselineComparisonMetrics,
    ) -> bool:
        if prop.net_pnl > base.net_pnl:
            return True
        return prop.net_pnl == base.net_pnl and prop.profit_factor >= base.profit_factor

    @staticmethod
    def _build_baseline_verdict(
            improves: bool,
            pnl_delta: Decimal,
            pnl_improvement_pct: float,
            prop_metrics: BaselineComparisonMetrics,
            base_metrics: BaselineComparisonMetrics,
    ) -> str:
        if improves and pnl_delta > Decimal(0):
            return (
                f"Proposed weights demonstrated out-of-sample outperformance: "
                f"+{pnl_delta:.2f} P&L ({pnl_improvement_pct:+.1f}%) over unchanged baseline."
            )
        if prop_metrics.net_pnl == base_metrics.net_pnl:
            return "Proposed weights matched unchanged baseline performance out-of-sample."
        return (
            f"Proposed weights underperformed unchanged baseline out-of-sample: "
            f"{pnl_delta:.2f} P&L ({pnl_improvement_pct:+.1f}%). Retaining current configuration recommended."
        )
