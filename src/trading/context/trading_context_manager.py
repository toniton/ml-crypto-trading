import time

from api.interfaces.trading_context import TradingContext
from api.interfaces.order import Order


class TradingContextManager:
    def __init__(self):
        self.trading_contexts: dict[str, TradingContext] = {}

    def register_trading_context(self, ticker_symbol: str, trading_context: TradingContext):
        self.trading_contexts[ticker_symbol] = trading_context

    def get_trading_context(self, ticker_symbol: str) -> TradingContext:
        return self.trading_contexts[ticker_symbol]

    def record_buy(self, ticker_symbol: str, order: Order):
        price = float(order.price)
        quantity = float(order.quantity)
        buy_price = price * quantity
        self.trading_contexts[ticker_symbol].available_balance -= buy_price
        self.trading_contexts[ticker_symbol].lowest_buy = min(self.trading_contexts[ticker_symbol].lowest_buy, price)
        self.trading_contexts[ticker_symbol].highest_buy = max(self.trading_contexts[ticker_symbol].highest_buy, price)
        self.trading_contexts[ticker_symbol].buy_count += 1
        self.trading_contexts[ticker_symbol].open_positions.append(order)
        self.trading_contexts[ticker_symbol].last_activity_time = time.time()

    def record_sell(self, ticker_symbol: str, order: Order):
        price = float(order.price)
        quantity = float(order.quantity)
        sell_price = price * quantity
        self.trading_contexts[ticker_symbol].closing_balance += sell_price
        self.trading_contexts[ticker_symbol].close_positions.append(order)
        self.trading_contexts[ticker_symbol].lowest_sell = min(self.trading_contexts[ticker_symbol].lowest_sell, price)
        self.trading_contexts[ticker_symbol].highest_sell = max(self.trading_contexts[ticker_symbol].highest_sell, price)
        self.trading_contexts[ticker_symbol].last_activity_time = time.time()
    