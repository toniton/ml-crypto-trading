from collections import abc
from decimal import Decimal
from typing import Optional

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction


class SimulatedAccount:
    def __init__(self, initial_balance: Decimal = Decimal("10000.0")):
        self._balances: dict[str, Decimal] = {"USD": initial_balance}
        self._orders: dict[str, Order] = {}

    def get_balance(self, currency: str) -> Decimal:
        return self._balances.get(currency, Decimal("0.0"))

    def set_balance(self, currency: str, amount: Decimal):
        self._balances[currency] = amount

    def update_balance(self, currency: str, delta: Decimal):
        current = self.get_balance(currency)
        self._balances[currency] = current + delta

    def get_balances(self) -> abc.ItemsView[str, Decimal]:
        return self._balances.items()

    def lock_funds(self, currency: str, amount: Decimal):
        current = self.get_balance(currency)
        if current >= amount:
            self._balances[currency] = current - amount
        else:
            raise ValueError(f"Insufficient funds for {currency}. Required: {amount}, Available: {current}")

    def add_order(self, order: Order):
        self._orders[order.uuid] = order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def cancel_order(self, order_id: str):
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                # In a more complex simulation, we would unlock funds here.

    def execute_order(self, order: Order):
        # Determine the delimiter used (supporting _, -, and /)
        if "_" in order.ticker_symbol:
            delimiter = "_"
        elif "-" in order.ticker_symbol:
            delimiter = "-"
        elif "/" in order.ticker_symbol:
            delimiter = "/"
        else:
            raise ValueError(f"Unsupported ticker symbol format: {order.ticker_symbol}")

        parts = order.ticker_symbol.split(delimiter)
        if len(parts) != 2:
            raise ValueError(f"Unsupported ticker symbol format: {order.ticker_symbol}")

        base, quote = parts
        quantity = Decimal(order.quantity)
        price = Decimal(order.price)
        total_quote = quantity * price

        if order.trade_action == TradeAction.BUY:
            self.lock_funds(quote, total_quote)
            self.update_balance(base, quantity)
        elif order.trade_action == TradeAction.SELL:
            self.lock_funds(base, quantity)
            self.update_balance(quote, total_quote)

        order.status = OrderStatus.COMPLETED
