from dataclasses import dataclass

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order


@dataclass
class Event:
    pass


@dataclass
class TickEvent(Event):
    timestamp: int


@dataclass
class MarketDataEvent(Event):
    market_data: MarketData
    ticker_symbol: str


@dataclass
class CandlesEvent(Event):
    candles: list[Candle]
    ticker_symbol: str


@dataclass
class OrderFilledEvent(Event):
    order: Order


# Backward-compatible alias
OrderFillEvent = OrderFilledEvent


@dataclass
class OrderCancelledEvent(Event):
    order: Order


@dataclass
class BalanceUpdateEvent(Event):
    balances: list[AccountBalance]
