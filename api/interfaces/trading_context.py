import dataclasses
import time
from math import inf

from pydantic.dataclasses import dataclass

from api.interfaces.order import Order


@dataclass
class TradingContext:
    starting_balance: float
    start_time: float = time.time()
    end_time: float = time.time()
    available_balance: float = 0
    closing_balance: float = 0
    buy_count: int = 0
    lowest_buy: float = inf
    highest_buy: float = -inf
    lowest_sell: float = inf
    highest_sell: float = -inf
    open_positions: list[Order] = dataclasses.field(default_factory=lambda: [])
    close_positions: list[Order] = dataclasses.field(default_factory=lambda: [])
    last_activity_time: float = time.time()

    def __post_init__(self):
        self.available_balance = self.starting_balance
