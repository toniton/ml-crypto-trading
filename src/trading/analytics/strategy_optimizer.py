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

        if total_trades < 3:
            rec_weight = current_w
            rationale = f"Insufficient sample size ({total_trades} trades); maintaining weight at {current_w:.2f}."
        else:
            ratio = score / avg_score if avg_score > 0 else 1.0
            rec_weight = max(min_weight, min(max_weight, round(current_w * ratio, 2)))
            if rec_weight > current_w:
                delta = rec_weight - current_w
                rationale = (
                    f"Strong performance (Win Rate: {wr:.1f}%, PF: {pf:.2f}); "
                    f"recommended increase by +{delta:.2f} to {rec_weight:.2f}."
                )
            elif rec_weight < current_w:
                delta = current_w - rec_weight
                rationale = (
                    f"Subpar performance (Win Rate: {wr:.1f}%, PF: {pf:.2f}); "
                    f"recommended reduction by -{delta:.2f} to {rec_weight:.2f}."
                )
            else:
                rationale = (
                    f"Balanced performance (Win Rate: {wr:.1f}%, PF: {pf:.2f}); "
                    f"optimal weight is {current_w:.2f}."
                )

        return StrategyCalibrationRecommendation(
            strategy_name=name,
            current_weight=current_w,
            recommended_weight=rec_weight,
            profit_factor=pf,
            win_rate_pct=wr,
            total_trades=total_trades,
            rationale=rationale,
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
        current_weights = {
            strat.get("name", f"Strategy_{i}"): float(strat.get("weight", 1.0))
            for i, strat in enumerate(strategies_config)
            if strat.get("name")
        }

        calibrations = cls.calibrate_strategy_weights(trades, current_weights)
        suggested_windows = cls.optimize_trading_windows(trades, timezone_str=timezone_str)

        changes: list[ConfigChange] = [
            ConfigChange(
                path=f"assets.{ticker_symbol}.strategies.{cal.strategy_name}.weight",
                old_value=cal.current_weight,
                new_value=cal.recommended_weight,
                reason=cal.rationale,
            )
            for cal in calibrations
            if cal.recommended_weight != cal.current_weight
        ]
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

        summary = (
            f"Autonomous calibration for {ticker_symbol}: "
            f"{len(calibrations)} strategy weight(s) evaluated and "
            f"{len(suggested_windows)} optimal trading window(s) discovered."
        )

        return ConfigurationProposal(
            summary=summary,
            changes=changes,
            risks=[
                "Calibrated weights are based on historical sample performance and may need periodic re-evaluation.",
                "Narrowed trading windows will prevent signals during historically low-win-rate intervals.",
            ],
            expected_effect=(
                "Aligns strategy influence with empirical risk-adjusted performance "
                "and restricts trading to high-probability windows."
            ),
            base_commit_hash=base_commit_hash,
        )
