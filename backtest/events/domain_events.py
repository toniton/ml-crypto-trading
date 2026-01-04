from dataclasses import dataclass

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.account_balance import AccountBalance

@dataclass
class Event:
    """Base class for all backtest events."""
    pass

@dataclass
class TickEvent(Event):
    """Event emitted when the clock ticks."""
    timestamp: int

@dataclass
class MarketDataEvent(Event):
    """Event emitted when new market data is available."""
    market_data: MarketData
    ticker_symbol: str

@dataclass
class CandlesEvent(Event):
    """Event emitted when new candle is available."""
    candles: list[Candle]
    ticker_symbol: str

@dataclass
class OrderFillEvent(Event):
    """Event emitted when an order is filled or updated."""
    order: Order

@dataclass
class BalanceUpdateEvent(Event):
    """Event emitted when account balance changes."""
    balances: list[AccountBalance]
