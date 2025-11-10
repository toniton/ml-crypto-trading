import time

from api.interfaces.trading_context import TradingContext
from api.interfaces.order import Order


class TradingContextManager:
    def __init__(self):
        self.trading_contexts: dict[int, TradingContext] = {}

    def register_trading_context(self, asset_key: int, trading_context: TradingContext):
        self.trading_contexts[asset_key] = trading_context

    def get_trading_context(self, asset_key: int) -> TradingContext:
        return self.trading_contexts[asset_key]

    def record_buy(self, asset_key: int, order: Order):
        price = float(order.price)
        quantity = float(order.quantity)
        buy_price = price * quantity
        self.trading_contexts[asset_key].available_balance -= buy_price
        self.trading_contexts[asset_key].lowest_buy = min(self.trading_contexts[asset_key].lowest_buy, price)
        self.trading_contexts[asset_key].highest_buy = max(self.trading_contexts[asset_key].highest_buy, price)
        self.trading_contexts[asset_key].buy_count += 1
        self.trading_contexts[asset_key].open_positions.append(order)
        self.trading_contexts[asset_key].last_activity_time = time.time()

    def record_sell(self, asset_key: int, closed_order: Order):
        price = float(closed_order.price)
        quantity = float(closed_order.quantity)
        sell_price = price * quantity
        open_positions = self.trading_contexts[asset_key].open_positions
        self.trading_contexts[asset_key].available_balance += sell_price
        self.trading_contexts[asset_key].closing_balance += sell_price
        self.trading_contexts[asset_key].close_positions.append(closed_order)
        self.trading_contexts[asset_key].lowest_sell = min(self.trading_contexts[asset_key].lowest_sell, price)
        self.trading_contexts[asset_key].highest_sell = max(self.trading_contexts[asset_key].highest_sell, price)
        self.trading_contexts[asset_key].last_activity_time = time.time()
        self.trading_contexts[asset_key].open_positions = [
            open_order for open_order in open_positions if open_order.uuid != closed_order.uuid
        ]
