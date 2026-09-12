from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Optional

from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.domain.metrics import BacktestMetrics, BacktestSummary
from src.backtest.domain.result import BacktestFill, BacktestResult, PortfolioSnapshot
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
        round_trips, win_rate_pct, profit_factor = self._calculate_trade_metrics(fills)
        total_fees = sum((fill.fee for fill in fills), Decimal("0"))
        total_slippage_cost = sum((fill.slippage_cost for fill in fills), Decimal("0"))
        sharpe_ratio = self._calculate_sharpe_ratio(result.portfolio_snapshots)
        equity_curve = self._build_equity_curve(result.portfolio_snapshots)

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
            total_pnl=absolute_pnl,
            sharpe_ratio=sharpe_ratio,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            total_trades=round_trips,
            total_orders=len(orders),
            total_fills=len(fills),
            equity_curve=equity_curve,
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
    def _calculate_trade_metrics(fills: list[BacktestFill]) -> tuple[int, Optional[Decimal], Optional[Decimal]]:
        """Calculate completed round-trip trades, win rate percentage, and profit factor using FIFO matching."""
        buy_lots: list[list[Decimal]] = []
        trade_pnls: list[Decimal] = []

        for fill in fills:
            if fill.trade_action == TradeAction.BUY:
                fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal("0") else Decimal("0")
                buy_lots.append([fill.quantity, fill.execution_price, fee_per_unit])
            elif fill.trade_action == TradeAction.SELL:
                sell_qty = fill.quantity
                sell_price = fill.execution_price
                sell_fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal("0") else Decimal("0")

                while sell_qty > Decimal("0") and buy_lots:
                    buy_lot = buy_lots[0]
                    matched_qty = min(sell_qty, buy_lot[0])
                    buy_price = buy_lot[1]
                    buy_fee_unit = buy_lot[2]

                    cost = (buy_price + buy_fee_unit) * matched_qty
                    proceeds = (sell_price - sell_fee_per_unit) * matched_qty
                    pnl = proceeds - cost
                    trade_pnls.append(pnl)

                    buy_lot[0] -= matched_qty
                    sell_qty -= matched_qty
                    if buy_lot[0] <= Decimal("0"):
                        buy_lots.pop(0)

        round_trips = len(trade_pnls)
        if round_trips == 0:
            return 0, None, Decimal("1.00")

        winning_trades = sum(1 for pnl in trade_pnls if pnl > Decimal("0"))
        win_rate_pct = (Decimal(winning_trades) / Decimal(round_trips)) * Decimal("100")

        gross_profit = sum((pnl for pnl in trade_pnls if pnl > Decimal("0")), Decimal("0"))
        gross_loss = sum((abs(pnl) for pnl in trade_pnls if pnl < Decimal("0")), Decimal("0"))

        if gross_loss > Decimal("0"):
            profit_factor = gross_profit / gross_loss
        elif gross_profit > Decimal("0"):
            profit_factor = Decimal("100.00")
        else:
            profit_factor = Decimal("1.00")

        return round_trips, Decimal(f"{win_rate_pct:.2f}"), Decimal(f"{profit_factor:.2f}")

    @staticmethod
    def _calculate_sharpe_ratio(snapshots: list[PortfolioSnapshot]) -> Optional[Decimal]:
        if len(snapshots) < 2:
            return None

        returns: list[float] = []
        for i in range(1, len(snapshots)):
            prev_eq = float(snapshots[i - 1].equity)
            curr_eq = float(snapshots[i].equity)
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)

        if len(returns) < 2:
            return None

        mean_return = math.fsum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return None

        total_time_span = snapshots[-1].timestamp - snapshots[0].timestamp
        avg_step = total_time_span / (len(snapshots) - 1) if len(snapshots) > 1 else 0

        if avg_step > 1000000:
            avg_step /= 1000.0

        seconds_per_year = 365.25 * 24 * 3600
        if avg_step > 0:
            periods_per_year = seconds_per_year / avg_step
            annual_factor = math.sqrt(periods_per_year)
        else:
            annual_factor = math.sqrt(252)

        sharpe = (mean_return / std_dev) * annual_factor
        return Decimal(f"{sharpe:.4f}")

    @staticmethod
    def _build_equity_curve(snapshots: list[PortfolioSnapshot]) -> list[dict[str, Any]]:
        if not snapshots:
            return []

        max_curve_points = 500
        if len(snapshots) <= max_curve_points:
            selected_snapshots = snapshots
        else:
            step = len(snapshots) / max_curve_points
            selected_indices = {int(i * step) for i in range(max_curve_points)}
            selected_indices.add(0)
            selected_indices.add(len(snapshots) - 1)
            selected_snapshots = [snapshots[i] for i in sorted(selected_indices) if i < len(snapshots)]

        curve = []
        for s in selected_snapshots:
            ts = int(s.timestamp * 1000) if s.timestamp < 100000000000 else int(s.timestamp)
            curve.append({
                "timestamp": ts,
                "equity": float(s.equity),
                "balance": float(s.cash),
            })
        return curve
