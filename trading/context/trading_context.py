from math import inf

import time

from entities.order import Order


class TradingContext:
    # open_positions: list[Order]

    def __enter__(self):
        self.start_time = time.time()

    def __init__(self, balance: float):
        self.starting_balance = balance
        self.available_balance = balance
        self.closing_balance = 0
        self.buy_count = 0
        self.lowest_buy = inf
        self.highest_buy = -inf
        self.lowest_sell = inf
        self.highest_sell = -inf
        self.open_positions = []

    def record_buy(self, order: Order):
        price = order.price
        buy_price = float(price)
        self.available_balance -= buy_price
        self.lowest_buy = min(self.lowest_buy, buy_price)
        self.highest_buy = max(self.highest_buy, buy_price)
        self.buy_count += 1
        self.open_positions.append(order)

    def record_sell(self, order: Order):
        (price) = order
        sell_price = float(price)
        self.closing_balance += sell_price
        self.lowest_sell = min(self.lowest_sell, sell_price)
        self.highest_sell = max(self.highest_sell, sell_price)
