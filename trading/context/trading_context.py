from math import inf

import time

from entities.order import Order


class TradingContext:
    # open_positions: list[Order]

    def __init__(self, balance: float):
        self.start_time = time.time()
        self.end_time = None
        self.starting_balance = balance
        self.available_balance = balance
        self.closing_balance = 0
        self.buy_count = 0
        self.lowest_buy = inf
        self.highest_buy = -inf
        self.lowest_sell = inf
        self.highest_sell = -inf
        self.open_positions = []

    def print_context(self):
        self.end_time = time.time()
        print("Trading Context")
        print(["self.start_time", self.start_time])
        print(["self.starting_balance", self.starting_balance])
        print(["self.closing_balance", self.closing_balance])
        print(["self.buy_count", self.buy_count])
        print(["self.lowest_buy", self.lowest_buy])
        print(["self.highest_buy", self.highest_buy])
        print(["self.lowest_sell", self.lowest_sell])
        print(["self.highest_sell", self.highest_sell])
        print(["self.open_positions", self.open_positions])
        print(["self.end_time", self.end_time])

    def record_buy(self, order: Order):
        price = order.price
        buy_price = float(price)
        self.available_balance -= buy_price
        self.lowest_buy = min(self.lowest_buy, buy_price)
        self.highest_buy = max(self.highest_buy, buy_price)
        self.buy_count += 1
        self.open_positions.append(order)

    def record_sell(self, order: Order):
        price = order.price
        sell_price = float(price)
        self.closing_balance += sell_price
        self.lowest_sell = min(self.lowest_sell, sell_price)
        self.highest_sell = max(self.highest_sell, sell_price)
