from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from api.interfaces.trade import Trade


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class AttributionMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    win_rate_pct: float
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    net_pnl: Decimal
    profit_factor: float
    avg_return_pct: float
    avg_duration_seconds: float
    max_win: Decimal
    max_loss: Decimal


class TradeAttributionService:
    """Calculates multidimensional P&L attribution and execution statistics across trades."""

    @classmethod
    def calculate_metrics(cls, trades: list[Trade]) -> AttributionMetrics:
        if not trades:
            return cls._empty_metrics()

        total = len(trades)
        wins, losses, break_even, win_rate = cls._compute_outcome_counts(trades, total)
        pnl = cls._compute_pnl_totals(trades)
        stats = cls._compute_summary_stats(trades, total)

        return AttributionMetrics(
            total_trades=total,
            winning_trades=wins,
            losing_trades=losses,
            break_even_trades=break_even,
            win_rate_pct=win_rate,
            gross_pnl=pnl[0],
            total_fees=pnl[1],
            total_slippage=pnl[2],
            net_pnl=pnl[3],
            profit_factor=cls._compute_profit_factor(trades),
            avg_return_pct=stats[0],
            avg_duration_seconds=stats[1],
            max_win=stats[2],
            max_loss=stats[3],
        )

    @staticmethod
    def _compute_outcome_counts(trades: list[Trade], total: int) -> tuple[int, int, int, float]:
        wins = sum(1 for t in trades if t.net_pnl > Decimal(0))
        losses = sum(1 for t in trades if t.net_pnl < Decimal(0))
        break_even = sum(1 for t in trades if t.net_pnl == Decimal(0))
        win_rate = round((wins / total * 100.0) if total > 0 else 0.0, 2)
        return wins, losses, break_even, win_rate

    @staticmethod
    def _compute_pnl_totals(trades: list[Trade]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        gross = sum((t.gross_pnl for t in trades), Decimal(0))
        fees = sum((t.fees for t in trades), Decimal(0))
        slippage = sum((t.slippage for t in trades), Decimal(0))
        net = sum((t.net_pnl for t in trades), Decimal(0))
        return gross, fees, slippage, net

    @staticmethod
    def _compute_profit_factor(trades: list[Trade]) -> float:
        gross_wins = sum((t.net_pnl for t in trades if t.net_pnl > Decimal(0)), Decimal(0))
        gross_losses = abs(sum((t.net_pnl for t in trades if t.net_pnl < Decimal(0)), Decimal(0)))
        if gross_losses > Decimal(0):
            return round(float(gross_wins / gross_losses), 2)
        if gross_wins > Decimal(0):
            return 999.99
        return 0.0

    @staticmethod
    def _compute_summary_stats(trades: list[Trade], total: int) -> tuple[float, float, Decimal, Decimal]:
        avg_ret = round(float(sum((t.return_pct for t in trades), Decimal(0)) / Decimal(total)), 4)
        avg_dur = round(sum(t.duration_seconds for t in trades) / total, 2)
        max_win = max((t.net_pnl for t in trades), default=Decimal(0))
        max_loss = min((t.net_pnl for t in trades), default=Decimal(0))
        return avg_ret, avg_dur, max_win, max_loss

    @classmethod
    def attribute_by_commit(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            commit = trade.commit_hash or "UNKNOWN"
            grouped[commit].append(trade)
        return {commit: cls.calculate_metrics(group) for commit, group in grouped.items()}

    @classmethod
    def attribute_by_strategy(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            strategy = trade.winning_strategy or "UNKNOWN"
            grouped[strategy].append(trade)
        return {strategy: cls.calculate_metrics(group) for strategy, group in grouped.items()}

    @classmethod
    def attribute_by_symbol(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            grouped[trade.ticker_symbol].append(trade)
        return {symbol: cls.calculate_metrics(group) for symbol, group in grouped.items()}

    @staticmethod
    def _empty_metrics() -> AttributionMetrics:
        return AttributionMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            break_even_trades=0,
            win_rate_pct=0.0,
            gross_pnl=Decimal(0),
            total_fees=Decimal(0),
            total_slippage=Decimal(0),
            net_pnl=Decimal(0),
            profit_factor=0.0,
            avg_return_pct=0.0,
            avg_duration_seconds=0.0,
            max_win=Decimal(0),
            max_loss=Decimal(0),
        )
