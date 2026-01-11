from dataclasses import field
from decimal import Decimal
from math import inf
from typing import Optional

from pydantic.dataclasses import dataclass

from api.interfaces.market_data import MarketData


@dataclass
class TradingContext:
    ticker_symbol: str
    exchange: str
    starting_balance: Decimal
    available_balance: Decimal = 0
    closing_balance: Decimal = 0
    lowest_buy: float = inf
    highest_buy: float = -inf
    lowest_sell: float = inf
    highest_sell: float = -inf
    open_positions: list[MarketData] = field(default_factory=list)
    close_positions: list[MarketData] = field(default_factory=list)
    last_market_activity_time: Optional[float] = None

    def __post_init__(self):
        self.available_balance = self.starting_balance

    @property
    def buy_count(self) -> int:
        return len(self.open_positions)

    @property
    def total_positions(self) -> int:
        return len(self.open_positions) + len(self.close_positions)
