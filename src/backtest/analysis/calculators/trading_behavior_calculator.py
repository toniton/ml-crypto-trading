from __future__ import annotations

from decimal import Decimal
from typing import Optional

from api.interfaces.trade_action import TradeAction
from src.backtest.domain.metrics import TradingBehaviorMetrics
from src.backtest.domain.result import BacktestFill, PortfolioSnapshot


class TradingBehaviorCalculator:
    """Calculates trade distribution, expectancy, streak, turnover, and holding metrics."""

    def calculate(
            self,
            fills: list[BacktestFill],
            snapshots: list[PortfolioSnapshot],
            initial_balance: Decimal,
    ) -> TradingBehaviorMetrics:
        if not fills:
            return TradingBehaviorMetrics(turnover=Decimal("0.00"))

        buy_lots: list[list] = []  # [qty, buy_price, buy_fee_unit, submitted_at]
        trade_pnls: list[Decimal] = []
        holding_times: list[float] = []
        total_traded_volume = Decimal("0")

        for fill in fills:
            fill_volume = fill.execution_price * fill.quantity
            total_traded_volume += fill_volume

            if fill.trade_action == TradeAction.BUY:
                fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal("0") else Decimal("0")
                buy_lots.append([fill.quantity, fill.execution_price, fee_per_unit, fill.executed_at])
            elif fill.trade_action == TradeAction.SELL:
                sell_qty = fill.quantity
                sell_price = fill.execution_price
                sell_fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal("0") else Decimal("0")
                sell_time = fill.executed_at

                while sell_qty > Decimal("0") and buy_lots:
                    buy_lot = buy_lots[0]
                    matched_qty = min(sell_qty, buy_lot[0])
                    buy_price = buy_lot[1]
                    buy_fee_unit = buy_lot[2]
                    buy_time = buy_lot[3]

                    cost = (buy_price + buy_fee_unit) * matched_qty
                    proceeds = (sell_price - sell_fee_per_unit) * matched_qty
                    pnl = proceeds - cost
                    trade_pnls.append(pnl)

                    diff_sec = float(sell_time - buy_time)
                    if diff_sec > 100000000:
                        diff_sec /= 1000.0
                    holding_times.append(max(0.0, diff_sec))

                    buy_lot[0] -= matched_qty
                    sell_qty -= matched_qty
                    if buy_lot[0] <= Decimal("0"):
                        buy_lots.pop(0)

        round_trips = len(trade_pnls)
        turnover = (
            Decimal(f"{total_traded_volume / initial_balance:.2f}")
            if initial_balance > Decimal("0")
            else Decimal("0.00")
        )
        exposure_pct = self._calculate_exposure_pct(snapshots)

        if round_trips == 0:
            return TradingBehaviorMetrics(
                turnover=turnover,
                exposure_time_pct=exposure_pct,
            )

        winning_pnls = [p for p in trade_pnls if p > Decimal("0")]
        losing_pnls = [p for p in trade_pnls if p < Decimal("0")]

        winning_trades = len(winning_pnls)
        losing_trades = len(losing_pnls)
        win_rate_pct = Decimal(f"{(winning_trades / round_trips) * 100:.2f}")

        gross_profit = sum(winning_pnls, Decimal("0"))
        gross_loss = sum((abs(p) for p in losing_pnls), Decimal("0"))

        if gross_loss > Decimal("0"):
            profit_factor = Decimal(f"{gross_profit / gross_loss:.2f}")
        elif gross_profit > Decimal("0"):
            profit_factor = Decimal("100.00")
        else:
            profit_factor = Decimal("1.00")

        total_net_pnl = sum(trade_pnls, Decimal("0"))
        expectancy = Decimal(f"{total_net_pnl / round_trips:.2f}")

        average_win: Optional[Decimal] = (
            Decimal(f"{gross_profit / winning_trades:.2f}") if winning_trades > 0 else None
        )
        average_loss: Optional[Decimal] = (
            Decimal(f"{gross_loss / losing_trades:.2f}") if losing_trades > 0 else None
        )

        win_loss_ratio: Optional[Decimal] = (
            Decimal(f"{average_win / average_loss:.2f}")
            if average_win is not None and average_loss is not None and average_loss > Decimal("0")
            else None
        )

        largest_win: Optional[Decimal] = (
            Decimal(f"{max(winning_pnls):.2f}") if winning_pnls else None
        )
        largest_loss: Optional[Decimal] = (
            Decimal(f"{min(losing_pnls):.2f}") if losing_pnls else None
        )

        max_consec_wins, max_consec_losses = self._calculate_consecutive_streaks(trade_pnls)
        avg_holding_time = (
            sum(holding_times) / len(holding_times) if holding_times else 0.0
        )

        # Expectancy ratio: (win_rate * avg_win - loss_rate * avg_loss)
        expectancy_ratio: Optional[Decimal] = None
        if average_win is not None and average_loss is not None:
            win_prob = Decimal(winning_trades) / Decimal(round_trips)
            loss_prob = Decimal(losing_trades) / Decimal(round_trips)
            expectancy_ratio = Decimal(f"{(win_prob * average_win) - (loss_prob * average_loss):.2f}")

        return TradingBehaviorMetrics(
            profit_factor=profit_factor,
            expectancy=expectancy,
            expectancy_ratio=expectancy_ratio,
            win_rate_pct=win_rate_pct,
            win_loss_ratio=win_loss_ratio,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            turnover=turnover,
            avg_holding_time_seconds=avg_holding_time,
            exposure_time_pct=exposure_pct,
            round_trips=round_trips,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
        )

    @staticmethod
    def _calculate_consecutive_streaks(trade_pnls: list[Decimal]) -> tuple[int, int]:
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in trade_pnls:
            if pnl > Decimal("0"):
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < Decimal("0"):
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        return max_wins, max_losses

    @staticmethod
    def _calculate_exposure_pct(snapshots: list[PortfolioSnapshot]) -> Decimal:
        if not snapshots:
            return Decimal("0.00")
        active_snapshots = 0
        for s in snapshots:
            has_position = any(qty > Decimal("0") for qty in s.positions.values())
            if has_position:
                active_snapshots += 1
        pct = (active_snapshots / len(snapshots)) * 100.0
        return Decimal(f"{pct:.2f}")
