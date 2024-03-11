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
        price = order.price
        buy_price = float(price)
        self.trading_contexts[ticker_symbol].available_balance -= buy_price
        self.trading_contexts[ticker_symbol].lowest_buy = min(self.trading_contexts[ticker_symbol].lowest_buy, buy_price)
        self.trading_contexts[ticker_symbol].highest_buy = max(self.trading_contexts[ticker_symbol].highest_buy, buy_price)
        self.trading_contexts[ticker_symbol].buy_count += 1
        self.trading_contexts[ticker_symbol].open_positions.append(order)

    def record_sell(self, ticker_symbol: str, order: Order):
        price = order.price
        sell_price = float(price)
        self.trading_contexts[ticker_symbol].closing_balance += sell_price
        self.trading_contexts[ticker_symbol].lowest_sell = min(self.trading_contexts[ticker_symbol].lowest_sell, sell_price)
        self.trading_contexts[ticker_symbol].highest_sell = max(self.trading_contexts[ticker_symbol].highest_sell, sell_price)

    def print_context(self) -> None:
        for key, value in self.trading_contexts.items():
            print(value.lowest_buy)
            value.end_time = time.time()
            print("Trading Context")
            print(f"======= {key} =======================")
            print(["self.start_time", value.start_time])
            print(["self.starting_balance", value.starting_balance])
            print(["self.closing_balance", value.closing_balance])
            print(["self.buy_count", value.buy_count])
            print(["self.lowest_buy", value.lowest_buy])
            print(["self.highest_buy", value.highest_buy])
            print(["self.lowest_sell", value.lowest_sell])
            print(["self.highest_sell", value.highest_sell])
            print(["self.open_positions", value.open_positions])
            print(["self.end_time", value.end_time])
    