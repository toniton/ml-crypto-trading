from decimal import Decimal
from typing import Optional, List
from api.interfaces.market_data import MarketData


class PortfolioHelper:
    @staticmethod
    def _get_active_holdings(
            open_positions: List[MarketData],
            close_positions: List[MarketData]
    ) -> List[Decimal]:
        """
        Matches one sell to one buy (1-to-1 matching) and returns prices of remaining buys.
        """
        buys = sorted(open_positions, key=lambda x: x.timestamp)
        sells = sorted(close_positions, key=lambda x: x.timestamp)

        inventory = [Decimal(b.close_price) for b in buys]

        for _ in sells:
            if inventory:
                inventory.pop(0)

        return inventory

    @staticmethod
    def calculate_portfolio_value(
            available_balance: Decimal,
            current_price: str,
            open_positions: list[MarketData],
            close_positions: list[MarketData] = None
    ) -> Decimal:
        portfolio_value = available_balance
        current_price_decimal = Decimal(current_price)
        active_holdings = PortfolioHelper._get_active_holdings(open_positions, close_positions or [])
        for _ in active_holdings:
            portfolio_value += current_price_decimal
        return portfolio_value

    @staticmethod
    def calculate_unrealized_pnl_value(
            starting_balance: Decimal,
            current_price: str,
            open_positions: list[MarketData],
            close_positions: list[MarketData]
    ) -> Decimal:
        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        current_price_decimal = Decimal(current_price)
        active_holdings = PortfolioHelper._get_active_holdings(open_positions, close_positions)

        unrealized_pnl = Decimal("0.0")
        for buy_price in active_holdings:
            unrealized_pnl += (current_price_decimal - buy_price)

        return unrealized_pnl

    @staticmethod
    def calculate_peak_value(
            starting_balance: Decimal,
            open_positions: list[MarketData],
            closed_positions: list[MarketData]
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
            price = Decimal(trade.close_price)

            if is_buy:
                portfolio_value -= price
            else:
                portfolio_value += price

            if portfolio_value > peak_value:
                peak_value = portfolio_value
                peak_time = trade.timestamp

            if portfolio_value <= 0:
                return peak_value, peak_time

        return peak_value, peak_time

    @staticmethod
    def calculate_trough_value(
            starting_balance: Decimal,
            open_positions: list[MarketData],
            closed_positions: list[MarketData]
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
            price = Decimal(trade.close_price)

            if is_buy:
                portfolio_value -= price
            else:
                portfolio_value += price

            if portfolio_value < trough_value:
                trough_value = portfolio_value
                trough_time = trade.timestamp

            if portfolio_value <= 0:
                return trough_value, trough_time

        return trough_value, trough_time
