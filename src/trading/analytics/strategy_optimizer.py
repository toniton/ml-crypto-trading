from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
import math
from typing import Any, Optional
from zoneinfo import ZoneInfo

from api.interfaces.trade import Trade
from api.interfaces.walk_forward import WalkForwardRunSpec, WalkForwardSummary
from src.core.weekday import Weekday
from src.trading.analytics.trade_attribution_service import TradeAttributionService
from src.trading.strategies.models.strategy_schedule import TradingWindow
from src.vcs.domain.diff import ConfigChange, ConfigurationProposal
from src.walk_forward.runner.walk_forward_runner import WalkForwardRunner


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
    independent_windows: int = 0
    evidence_status: str = "INSUFFICIENT"


@dataclass(frozen=True)
class BaselineComparisonMetrics:
    net_pnl: Decimal
    gross_wins: Decimal
    gross_losses: Decimal
    profit_factor: float
    win_rate_pct: float
    trades_count: int
    max_drawdown: Decimal = Decimal(0)
    worst_trade_loss: Decimal = Decimal(0)
    return_volatility: float = 0.0


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
    drawdown_delta: Decimal = Decimal(0)
    risk_increased: bool = False


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
    def _calculate_sample_uncertainty(
            total_trades: int,
            win_rate_pct: float,
            independent_windows: Optional[int] = None,
    ) -> tuple[str, float]:
        if total_trades <= 0:
            return "LOW", 0.0
        p = win_rate_pct / 100.0
        variance = max(0.0, p * (1.0 - p))
        margin_of_error = round(1.96 * ((variance / total_trades) ** 0.5) * 100.0, 1)
        windows = (
            independent_windows
            if independent_windows is not None
            else (3 if total_trades >= 20 else (2 if total_trades >= 5 else 1))
        )
        if total_trades < 5 or windows < 2:
            confidence = "LOW"
        elif total_trades >= 20 and windows >= 3 and margin_of_error <= 22.0:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"
        return confidence, margin_of_error

    @staticmethod
    def _classify_evidence_status(
            total_trades: int,
            independent_windows: int,
            margin_of_error: float,
    ) -> str:
        if total_trades < 5 or independent_windows < 2:
            return "INSUFFICIENT"
        if total_trades >= 20 and independent_windows >= 3 and margin_of_error <= 22.0:
            return "SUFFICIENT"
        return "WEAK"

    @staticmethod
    def _count_strategy_independent_windows(trades: list[Trade], strategy_name: str) -> int:
        days: set[tuple[int, int, int]] = set()
        for trade in trades:
            attrs = trade.entry_strategy_attributions or {}
            if strategy_name in attrs or trade.winning_strategy == strategy_name:
                dt = datetime.fromtimestamp(trade.entry_timestamp, tz=timezone.utc)
                days.add((dt.year, dt.month, dt.day))
        return len(days)

    @staticmethod
    def _calculate_adjusted_weight(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    def _format_calibration_rationale(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            current_w: float,
            rec_weight: float,
            wr: float,
            moe: float,
            pf: float,
            confidence: str,
            total_trades: int,
            independent_windows: int = 1,
    ) -> str:
        if total_trades < 3:
            return (
                f"Insufficient sample size ({total_trades} trades); maintaining weight at {current_w:.2f} "
                f"(Confidence: {confidence})."
            )
        window_note = (
            f", Windows: {independent_windows}"
            if independent_windows < 2 and total_trades >= 5
            else ""
        )
        prefix = (
            f"(Win Rate: {wr:.1f}% ± {moe:.1f}%, PF: {pf:.2f}, "
            f"Confidence: {confidence}{window_note})"
        )
        if rec_weight > current_w:
            delta = rec_weight - current_w
            return f"Strong performance {prefix}; recommended increase by +{delta:.2f} to {rec_weight:.2f}."
        if rec_weight < current_w:
            delta = current_w - rec_weight
            return f"Subpar performance {prefix}; recommended reduction by -{delta:.2f} to {rec_weight:.2f}."
        return f"Balanced performance {prefix}; optimal weight is {current_w:.2f}."

    @classmethod
    def _create_calibration_recommendation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            name: str,
            current_w: float,
            score: float,
            avg_score: float,
            metrics: Any,
            min_weight: float,
            max_weight: float,
            independent_windows: int = 1,
    ) -> StrategyCalibrationRecommendation:
        total_trades = metrics.total_trades if metrics else 0
        pf = metrics.profit_factor if metrics else 0.0
        wr = metrics.win_rate_pct if metrics else 0.0
        confidence, moe = cls._calculate_sample_uncertainty(
            total_trades, wr, independent_windows=independent_windows
        )
        rec_weight = cls._calculate_adjusted_weight(
            current_w, score, avg_score, total_trades, min_weight, max_weight
        )
        return StrategyCalibrationRecommendation(
            strategy_name=name,
            current_weight=current_w,
            recommended_weight=rec_weight,
            profit_factor=pf,
            win_rate_pct=wr,
            total_trades=total_trades,
            rationale=cls._format_calibration_rationale(
                current_w, rec_weight, wr, moe, pf, confidence, total_trades, independent_windows
            ),
            confidence_level=confidence,
            sample_margin_of_error_pct=moe,
            independent_windows=independent_windows,
            evidence_status=cls._classify_evidence_status(
                total_trades, independent_windows, moe
            ),
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
                independent_windows=cls._count_strategy_independent_windows(trades, name),
            )
            for name, current_w in current_weights.items()
        ]

    @classmethod
    def profile_hourly_profitability(
            cls, trades: list[Trade], timezone_str: str = "UTC"
    ) -> list[HourlyProfitabilityProfile]:
        tz = ZoneInfo(timezone_str)
        hourly_buckets: dict[tuple[int, int], list[Trade]] = defaultdict(list)
        for trade in trades:
            dt = datetime.fromtimestamp(trade.entry_timestamp, tz=timezone.utc).astimezone(tz)
            hourly_buckets[(dt.weekday(), dt.hour)].append(trade)

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
            cls, profitable_slots: dict[Weekday, set[int]]
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
            cls, day_ranges: dict[Weekday, list[tuple[int, int]]]
    ) -> list[TradingWindow]:
        range_to_days: dict[tuple[int, int], list[Weekday]] = defaultdict(list)
        for weekday, ranges in day_ranges.items():
            for r in ranges:
                range_to_days[r].append(weekday)

        windows: list[TradingWindow] = []
        for (start_h, end_h), days in sorted(range_to_days.items(), key=lambda x: (x[0][0], x[0][1])):
            start_t = time(hour=start_h, minute=0, second=0)
            end_t = time(hour=23, minute=59, second=59) if end_h >= 24 else time(hour=end_h, minute=0, second=0)
            windows.append(TradingWindow(days=days, start_time=start_t, end_time=end_t))
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
        return cls._build_trading_windows_from_ranges(cls._extract_contiguous_day_ranges(profitable_slots))

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
            strategy_trades, timezone_str=timezone_str, min_trades=min_trades, min_win_rate=min_win_rate
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
    def _format_windows_payload(cls, windows: list[TradingWindow]) -> list[dict[str, Any]]:
        return [
            {
                "days": [d.value for d in w.days],
                "start_time": w.start_time.strftime("%H:%M:%S"),
                "end_time": w.end_time.strftime("%H:%M:%S"),
            }
            for w in windows
        ]

    @classmethod
    def _build_strategy_schedule_change(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
        strat_windows = (
            cls.optimize_strategy_trading_windows(trades, sname, timezone_str=timezone_str)
            if trades
            else []
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
    def _build_schedule_changes(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
                ticker_symbol, strat, suggested_windows, trades, timezone_str, allow_asset_fallback
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
            "Calibrated weights are preliminary empirical heuristics based on in-sample trade attribution.",
            "Narrowed trading windows will prevent signals during historically low-win-rate intervals.",
            "Full backtest and multi-fold walk-forward execution is required before live promotion.",
        ]
        if baseline_eval is not None:
            if baseline_eval.risk_increased:
                risks.append(
                    f"Measured risk trade-off: out-of-sample max drawdown increased by "
                    f"+{baseline_eval.drawdown_delta:.2f} (candidate {baseline_eval.proposed_metrics.max_drawdown:.2f} "
                    f"vs baseline {baseline_eval.baseline_metrics.max_drawdown:.2f})."
                )
            if not baseline_eval.demonstrates_improvement:
                risks.append(
                    f"Out-of-sample validation caution: {baseline_eval.verdict} "
                    f"Review recommended before applying."
                )
        if any(c.evidence_status == "INSUFFICIENT" for c in calibrations):
            risks.append(
                "One or more strategies have insufficient independent sample size or narrow window coverage."
            )
        effect = (
            f"Preliminary attribution diagnostic (in-sample calibration vs unseen out-of-sample split): "
            f"{baseline_eval.verdict}"
            if baseline_eval is not None
            else (
                "Preliminary attribution heuristic; insufficient trade count (<4) for "
                "out-of-sample split comparison."
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
    def _extract_candidate_strategy_windows(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            strategies_config: list[dict[str, Any]],
            suggested_windows: list[TradingWindow],
            in_sample_trades: list[Trade],
            timezone_str: str,
            allow_asset_fallback: bool,
    ) -> dict[str, list[TradingWindow]]:
        candidate_windows: dict[str, list[TradingWindow]] = {}
        for strat in strategies_config:
            sname = strat.get("name")
            if not sname:
                continue
            strat_wins = cls.optimize_strategy_trading_windows(
                in_sample_trades, sname, timezone_str=timezone_str
            )
            effective = strat_wins if strat_wins else (suggested_windows if allow_asset_fallback else [])
            if effective:
                candidate_windows[sname] = effective
        return candidate_windows

    @classmethod
    def _create_proposal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    def evaluate_candidate_diagnostics(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            current_asset_config: dict[str, Any],
            trades: list[Trade],
            timezone_str: str = "UTC",
            allow_asset_fallback: bool = False,
            train_ratio: float = 0.7,
    ) -> tuple[
        list[StrategyCalibrationRecommendation],
        list[TradingWindow],
        Optional[BaselineComparisonResult],
    ]:
        strategies_config = current_asset_config.get("strategies", [])
        current_weights = cls._extract_current_weights(strategies_config)
        in_sample = (
            cls._split_trades_chronologically(trades, train_ratio)[0]
            if len(trades) >= 4
            else list(trades)
        )
        calibrations = cls.calibrate_strategy_weights(in_sample, current_weights)
        suggested_windows = cls.optimize_trading_windows(in_sample, timezone_str=timezone_str)
        candidate_windows = cls._extract_candidate_strategy_windows(
            strategies_config, suggested_windows, in_sample, timezone_str, allow_asset_fallback
        )
        baseline_eval = cls.evaluate_split_sample_baseline(
            trades,
            current_weights,
            proposed_weights={c.strategy_name: c.recommended_weight for c in calibrations},
            train_ratio=train_ratio,
            strategy_windows=candidate_windows or None,
            timezone_str=timezone_str,
        )
        return calibrations, suggested_windows, baseline_eval

    @classmethod
    def generate_optimization_proposal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            ticker_symbol: str,
            current_asset_config: dict[str, Any],
            trades: list[Trade],
            timezone_str: str = "UTC",
            base_commit_hash: Optional[str] = None,
            allow_asset_fallback: bool = False,
            train_ratio: float = 0.7,
    ) -> ConfigurationProposal:
        strategies_config = current_asset_config.get("strategies", [])
        in_sample = (
            cls._split_trades_chronologically(trades, train_ratio)[0]
            if len(trades) >= 4
            else list(trades)
        )
        calibrations, suggested_windows, baseline_eval = cls.evaluate_candidate_diagnostics(
            current_asset_config=current_asset_config,
            trades=trades,
            timezone_str=timezone_str,
            allow_asset_fallback=allow_asset_fallback,
            train_ratio=train_ratio,
        )
        changes = cls._build_weight_changes(ticker_symbol, calibrations)
        changes.extend(
            cls._build_schedule_changes(
                ticker_symbol,
                strategies_config,
                suggested_windows,
                trades=in_sample,
                timezone_str=timezone_str,
                allow_asset_fallback=allow_asset_fallback,
            )
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
    def _evaluate_out_of_sample_comparison(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            out_of_sample: list[Trade],
            current_weights: dict[str, float],
            proposed_weights: dict[str, float],
            in_sample_count: int,
            strategy_windows: Optional[dict[str, list[TradingWindow]]] = None,
            timezone_str: str = "UTC",
    ) -> BaselineComparisonResult:
        base_metrics = cls._simulate_weighted_performance(out_of_sample, current_weights)
        prop_metrics = cls._simulate_weighted_performance(
            out_of_sample,
            proposed_weights,
            strategy_windows=strategy_windows,
            timezone_str=timezone_str,
        )
        pnl_delta = prop_metrics.net_pnl - base_metrics.net_pnl
        drawdown_delta = prop_metrics.max_drawdown - base_metrics.max_drawdown
        pnl_imp = cls._calculate_pnl_improvement(pnl_delta, base_metrics.net_pnl)
        risk_increased = cls._check_risk_increased(base_metrics, pnl_delta, drawdown_delta)
        improves = cls._check_demonstrates_improvement(
            prop_metrics, base_metrics, risk_increased=risk_increased
        )
        verdict = cls._build_baseline_verdict(
            improves,
            pnl_delta,
            pnl_imp,
            prop_metrics,
            base_metrics,
            drawdown_delta=drawdown_delta,
            risk_increased=risk_increased,
        )
        return BaselineComparisonResult(
            baseline_metrics=base_metrics,
            proposed_metrics=prop_metrics,
            equal_weight_metrics=cls._simulate_weighted_performance(
                out_of_sample, {s: 1.0 for s in current_weights}
            ),
            pnl_delta=pnl_delta,
            pnl_improvement_pct=pnl_imp,
            in_sample_trades_count=in_sample_count,
            out_of_sample_trades_count=len(out_of_sample),
            demonstrates_improvement=improves,
            verdict=verdict,
            drawdown_delta=drawdown_delta,
            risk_increased=risk_increased,
        )

    @classmethod
    def evaluate_walk_forward_baseline(
            cls,
            runner: WalkForwardRunner,
            spec: WalkForwardRunSpec,
    ) -> WalkForwardSummary:
        return runner.run(spec)

    @classmethod
    def evaluate_split_sample_baseline(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            trades: list[Trade],
            current_weights: dict[str, float],
            proposed_weights: Optional[dict[str, float]] = None,
            train_ratio: float = 0.7,
            strategy_windows: Optional[dict[str, list[TradingWindow]]] = None,
            timezone_str: str = "UTC",
    ) -> Optional[BaselineComparisonResult]:
        if not trades or not current_weights or len(trades) < 4:
            return None
        in_sample, out_of_sample = cls._split_trades_chronologically(trades, train_ratio)
        if not out_of_sample:
            return None
        if proposed_weights is None:
            recs = cls.calibrate_strategy_weights(in_sample, current_weights)
            proposed_weights = {rec.strategy_name: rec.recommended_weight for rec in recs}
        if not proposed_weights:
            return None
        return cls._evaluate_out_of_sample_comparison(
            out_of_sample,
            current_weights,
            proposed_weights,
            len(in_sample),
            strategy_windows=strategy_windows,
            timezone_str=timezone_str,
        )

    @classmethod
    def _simulate_weighted_performance(  # pylint: disable=too-many-locals
            cls,
            trades: list[Trade],
            weights: dict[str, float],
            strategy_windows: Optional[dict[str, list[TradingWindow]]] = None,
            timezone_str: str = "UTC",
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
        active_trades = 0
        cum_pnl = Decimal(0)
        peak_pnl = Decimal(0)
        max_drawdown = Decimal(0)
        worst_trade_loss = Decimal(0)
        trade_pnls: list[float] = []

        for trade in trades:
            trade_net = cls._calculate_trade_weighted_net(
                trade, weights, avg_w, strategy_windows=strategy_windows, timezone_str=timezone_str
            )
            if trade_net is None:
                continue
            active_trades += 1
            net_pnl += trade_net
            cum_pnl += trade_net
            peak_pnl = max(peak_pnl, cum_pnl)
            max_drawdown = max(max_drawdown, peak_pnl - cum_pnl)
            trade_pnls.append(float(trade_net))

            if trade_net > Decimal(0):
                gross_wins += trade_net
                winning_trades += 1
            elif trade_net < Decimal(0):
                loss_abs = abs(trade_net)
                gross_losses += loss_abs
                worst_trade_loss = max(worst_trade_loss, loss_abs)

        profit_factor = cls._calculate_profit_factor(gross_wins, gross_losses)
        win_rate = round((winning_trades / active_trades * 100.0), 2) if active_trades > 0 else 0.0
        volatility = cls._calculate_return_volatility(trade_pnls)

        return BaselineComparisonMetrics(
            net_pnl=net_pnl,
            gross_wins=gross_wins,
            gross_losses=gross_losses,
            profit_factor=profit_factor,
            win_rate_pct=win_rate,
            trades_count=active_trades,
            max_drawdown=round(max_drawdown, 4),
            worst_trade_loss=round(worst_trade_loss, 4),
            return_volatility=volatility,
        )

    @staticmethod
    def _calculate_return_volatility(trade_pnls: list[float]) -> float:
        if len(trade_pnls) < 2:
            return 0.0
        mean_val = sum(trade_pnls) / len(trade_pnls)
        variance = sum((val - mean_val) ** 2 for val in trade_pnls) / (len(trade_pnls) - 1)
        return round(math.sqrt(variance), 4)

    @staticmethod
    def _is_trade_within_windows(
            entry_timestamp: float,
            windows: list[TradingWindow],
            timezone_str: str,
    ) -> bool:
        if not windows:
            return True
        dt = datetime.fromtimestamp(entry_timestamp, tz=timezone.utc).astimezone(
            ZoneInfo(timezone_str)
        )
        weekday = Weekday(dt.weekday())
        trade_time = dt.time()
        for window in windows:
            if weekday in window.days and window.start_time <= trade_time <= window.end_time:
                return True
        return False

    @classmethod
    def _calculate_trade_weighted_net(
            cls,
            trade: Trade,
            weights: dict[str, float],
            avg_w: float,
            strategy_windows: Optional[dict[str, list[TradingWindow]]] = None,
            timezone_str: str = "UTC",
    ) -> Optional[Decimal]:
        attributions = trade.entry_strategy_attributions
        if not attributions:
            winning = trade.winning_strategy or "UNATTRIBUTED"
            attributions = {winning: 1.0}

        strat_mult = 0.0
        any_active = False
        for strat, share in attributions.items():
            if strategy_windows and strat in strategy_windows:
                if not cls._is_trade_within_windows(
                    trade.entry_timestamp, strategy_windows[strat], timezone_str
                ):
                    continue
            any_active = True
            strat_mult += float(weights.get(strat, 1.0)) * float(share)

        if not any_active:
            return None

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
    def _check_risk_increased(
            base: BaselineComparisonMetrics,
            pnl_delta: Decimal,
            drawdown_delta: Decimal,
    ) -> bool:
        if drawdown_delta <= Decimal(0):
            return False
        material_threshold = max(Decimal("5.0"), base.max_drawdown * Decimal("0.25"))
        if drawdown_delta > material_threshold:
            return True
        if drawdown_delta > pnl_delta > Decimal(0):
            return True
        return False

    @staticmethod
    def _check_demonstrates_improvement(
            prop: BaselineComparisonMetrics,
            base: BaselineComparisonMetrics,
            risk_increased: bool = False,
    ) -> bool:
        if risk_increased:
            return False
        if prop.net_pnl > base.net_pnl:
            return True
        return prop.net_pnl == base.net_pnl and prop.profit_factor >= base.profit_factor

    @staticmethod
    def _build_baseline_verdict(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            improves: bool,
            pnl_delta: Decimal,
            pnl_improvement_pct: float,
            prop_metrics: BaselineComparisonMetrics,
            base_metrics: BaselineComparisonMetrics,
            drawdown_delta: Decimal = Decimal(0),
            risk_increased: bool = False,
    ) -> str:
        if pnl_delta > Decimal(0) and risk_increased:
            return (
                f"Proposed configuration increased P&L (+{pnl_delta:.2f}, {pnl_improvement_pct:+.1f}%) "
                f"but materially increased max drawdown (+{drawdown_delta:.2f} to {prop_metrics.max_drawdown:.2f} "
                f"vs {base_metrics.max_drawdown:.2f} baseline). Higher return is accompanied by elevated "
                f"downside risk; retaining current configuration or running full walk-forward validation recommended."
            )
        if improves and pnl_delta > Decimal(0):
            return (
                f"Proposed weights demonstrated out-of-sample outperformance: "
                f"+{pnl_delta:.2f} P&L ({pnl_improvement_pct:+.1f}%), "
                f"max drawdown {prop_metrics.max_drawdown:.2f} (vs {base_metrics.max_drawdown:.2f} baseline) "
                f"over unchanged baseline."
            )
        if prop_metrics.net_pnl == base_metrics.net_pnl:
            return "Proposed weights matched unchanged baseline performance out-of-sample."
        return (
            f"Proposed weights underperformed unchanged baseline out-of-sample: "
            f"{pnl_delta:.2f} P&L ({pnl_improvement_pct:+.1f}%). Retaining current configuration recommended."
        )
