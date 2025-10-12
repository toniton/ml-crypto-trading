from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction


class PortfolioHelper:
    @staticmethod
    def calculate_portfolio_value(
        available_balance: float,
        current_price: str,
        open_positions: list[Order]
    ) -> float:
        portfolio_value = available_balance
        for order in open_positions:
            if order.trade_action == TradeAction.BUY:
                portfolio_value += (float(current_price) * float(order.quantity))
        return portfolio_value

    @staticmethod
    def calculate_unrealized_pnl_value(
        starting_balance: float,
        current_price: str,
        open_positions: list[Order],
        close_positions: list[Order]
    ) -> float:
        portfolio_value = starting_balance
        for order in open_positions:
            if order.trade_action == TradeAction.BUY:
                portfolio_value += ((float(current_price) - float(order.price)) * float(order.quantity))

        for order in close_positions:
            if order.trade_action == TradeAction.SELL:
                portfolio_value += ((float(current_price) - float(order.price)) * float(order.quantity))

        return portfolio_value - starting_balance

    @staticmethod
    def calculate_peak_value(starting_balance: float, positions: list[Order]) -> [float, float]:
        portfolio_value = starting_balance
        peak_value = starting_balance
        peak_time = 0

        for order in positions[:-1]:
            if order.trade_action == TradeAction.BUY:
                portfolio_value -= (float(order.price) * float(order.quantity))
            elif order.trade_action == TradeAction.SELL:
                portfolio_value += (float(order.price) * float(order.quantity))

            if portfolio_value > peak_value > 0:
                peak_value = portfolio_value
                peak_time = order.created_time

        return peak_value, peak_time

    @staticmethod
    def calculate_trough_value(starting_balance: float, positions: list[Order]) -> float:
        portfolio_value = starting_balance
        trough_value = starting_balance

        for order in positions:
            if order.trade_action == TradeAction.BUY:
                portfolio_value -= (float(order.price) * float(order.quantity))
            elif order.trade_action == TradeAction.SELL:
                portfolio_value += (float(order.price) * float(order.quantity))

            if 0 < portfolio_value < trough_value:
                trough_value = portfolio_value

        return trough_value
