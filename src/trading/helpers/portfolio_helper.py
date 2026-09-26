from decimal import Decimal
from typing import Optional, List
from api.interfaces.position_entry import PositionEntry


class PortfolioHelper:
    @staticmethod
    def _get_active_holdings(
            open_positions: List[PositionEntry],
            close_positions: List[PositionEntry]
    ) -> List[tuple[Decimal, Decimal]]:
        buys = sorted(open_positions, key=lambda x: x.timestamp)
        sells = sorted(close_positions, key=lambda x: x.timestamp)

        inventory: list[list[Decimal]] = [
            [
                Decimal(str(b.price)),
                Decimal(str(b.quantity)),
            ]
            for b in buys
        ]

        for s in sells:
            sell_qty = Decimal(str(s.quantity))
            while sell_qty > Decimal("0") and inventory:
                if inventory[0][1] <= sell_qty:
                    sell_qty -= inventory[0][1]
                    inventory.pop(0)
                else:
                    inventory[0][1] -= sell_qty
                    sell_qty = Decimal("0")

        return [(item[0], item[1]) for item in inventory if item[1] > Decimal("0")]

    @staticmethod
    def calculate_portfolio_value(
            available_balance: Decimal,
            current_price: str,
            open_positions: list[PositionEntry],
            close_positions: list[PositionEntry] = None
    ) -> Decimal:
        portfolio_value = available_balance
        current_price_decimal = Decimal(str(current_price))
        active_holdings = PortfolioHelper._get_active_holdings(open_positions, close_positions or [])
        for _, qty in active_holdings:
            portfolio_value += current_price_decimal * qty
        return portfolio_value

    @staticmethod
    def calculate_unrealized_pnl_value(
            starting_balance: Decimal,
            current_price: str,
            open_positions: list[PositionEntry],
            close_positions: list[PositionEntry]
    ) -> Decimal:
        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        current_price_decimal = Decimal(str(current_price))
        active_holdings = PortfolioHelper._get_active_holdings(open_positions, close_positions)

        unrealized_pnl = Decimal("0.0")
        for buy_price, qty in active_holdings:
            unrealized_pnl += (current_price_decimal - buy_price) * qty

        return unrealized_pnl

    @staticmethod
    def calculate_peak_value(
            starting_balance: Decimal,
            open_positions: list[PositionEntry],
            closed_positions: list[PositionEntry]
    ) -> tuple[Decimal, Optional[float]]:
        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        portfolio_value = starting_balance
        peak_value = starting_balance
        peak_time: Optional[float] = None

        all_trades = []
        for p in open_positions:
            all_trades.append((p, True))
        for p in closed_positions:
            all_trades.append((p, False))

        all_trades.sort(key=lambda x: x[0].timestamp)

        for trade, is_buy in all_trades:
            price = Decimal(str(trade.price))
            qty = Decimal(str(trade.quantity))
            trade_amount = price * qty

            if is_buy:
                portfolio_value -= trade_amount
            else:
                portfolio_value += trade_amount

            if portfolio_value > peak_value:
                peak_value = portfolio_value
                peak_time = trade.timestamp

            if portfolio_value <= 0:
                return peak_value, peak_time

        return peak_value, peak_time

    @staticmethod
    def calculate_trough_value(
            starting_balance: Decimal,
            open_positions: list[PositionEntry],
            closed_positions: list[PositionEntry]
    ) -> tuple[Decimal, Optional[float]]:
        portfolio_value = starting_balance
        trough_value = starting_balance
        trough_time: Optional[float] = None

        all_trades = []
        for p in open_positions:
            all_trades.append((p, True))
        for p in closed_positions:
            all_trades.append((p, False))

        all_trades.sort(key=lambda x: x[0].timestamp)

        for trade, is_buy in all_trades:
            price = Decimal(str(trade.price))
            qty = Decimal(str(trade.quantity))
            trade_amount = price * qty

            if is_buy:
                portfolio_value -= trade_amount
            else:
                portfolio_value += trade_amount

            if portfolio_value < trough_value:
                trough_value = portfolio_value
                trough_time = trade.timestamp

            if portfolio_value <= 0:
                return trough_value, trough_time

        return trough_value, trough_time
