from __future__ import annotations

from decimal import Decimal

from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.domain.metrics import BacktestMetrics, BacktestSummary
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession


class BacktestMetricsCalculator:
    def calculate(self, result: BacktestResult) -> BacktestMetrics:
        initial = result.initial_balance
        final = result.final_equity
        absolute_pnl = final - initial
        percentage_return = (
            (final / initial - Decimal("1")) * Decimal("100") if initial else Decimal("0")
        )

        peak = Decimal("0")
        max_drawdown = Decimal("0")
        for snapshot in result.portfolio_snapshots:
            peak = max(peak, snapshot.equity)
            max_drawdown = max(max_drawdown, peak - snapshot.equity)
        max_drawdown_pct = (max_drawdown / peak * Decimal("100")) if peak else Decimal("0")

        fills = result.fills
        orders = result.orders
        buy_count = sum(1 for fill in fills if fill.trade_action == TradeAction.BUY)
        sell_count = sum(1 for fill in fills if fill.trade_action == TradeAction.SELL)
        orders_cancelled = sum(1 for order in orders if order.status == OrderStatus.CANCELLED)
        round_trips = self._count_round_trips(fills)
        total_fees = sum((fill.fee for fill in fills), Decimal("0"))
        total_slippage_cost = sum((fill.slippage_cost for fill in fills), Decimal("0"))

        return BacktestMetrics(
            initial_balance=initial,
            final_equity=final,
            absolute_pnl=absolute_pnl,
            percentage_return=percentage_return,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            orders_submitted=len(orders),
            orders_filled=len(fills),
            orders_cancelled=orders_cancelled,
            buy_count=buy_count,
            sell_count=sell_count,
            round_trips=round_trips,
            total_fees=total_fees,
            total_slippage_cost=total_slippage_cost,
        )

    def summarize(self, session: BacktestSession, metrics: BacktestMetrics) -> BacktestSummary:
        return BacktestSummary(
            session_id=session.id,
            ticker_symbol=session.ticker_symbol,
            status=session.status.value,
            return_pct=metrics.percentage_return,
            absolute_pnl=metrics.absolute_pnl,
            max_drawdown_pct=metrics.max_drawdown_pct,
            round_trips=metrics.round_trips,
            orders_filled=metrics.orders_filled,
            orders_cancelled=metrics.orders_cancelled,
        )

    @staticmethod
    def _count_round_trips(fills) -> int:
        """Count completed buy→sell cycles using FIFO matching."""

        open_qty = Decimal("0")
        round_trips = 0
        for fill in fills:
            if fill.trade_action == TradeAction.BUY:
                open_qty += fill.quantity
            elif open_qty > 0:
                round_trips += 1
                open_qty = max(Decimal("0"), open_qty - fill.quantity)
        return round_trips
