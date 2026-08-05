from dataclasses import field
from decimal import Decimal
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
    lowest_buy: Decimal = Decimal('inf')
    highest_buy: Decimal = Decimal('-inf')
    lowest_sell: Decimal = Decimal('inf')
    highest_sell: Decimal = Decimal('-inf')
    open_positions: list[MarketData] = field(default_factory=list)
    close_positions: list[MarketData] = field(default_factory=list)
    position_qty: Decimal = Decimal(0)
    avg_entry_price: Decimal = Decimal(0)
    exit_qty: Decimal = Decimal(0)
    avg_exit_price: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    last_market_activity_time: Optional[float] = None
    commit_hash: Optional[str] = None

    def __post_init__(self):
        self.available_balance = self.starting_balance

    @property
    def buy_count(self) -> int:
        return len(self.open_positions)

    @property
    def total_positions(self) -> int:
        return len(self.open_positions) + len(self.close_positions)
