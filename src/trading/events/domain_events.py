from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.events.trading_event import TradingEvent


@dataclass
class MarketDataEvent(TradingEvent):
    ticker_symbol: str
    market_data: MarketData


@dataclass
class MarketStateChanged(TradingEvent):
    symbol: str
    price: Decimal
    market_timestamp: float


@dataclass
class OrderSubmitted(TradingEvent):
    symbol: str
    order: Order


@dataclass
class OrderExecuted(TradingEvent):
    symbol: str
    order: Order


@dataclass
class OrderCancelled(TradingEvent):
    symbol: str
    order: Order


@dataclass
class PositionChanged(TradingEvent):
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal
    position_qty: Decimal
    realized_pnl: Decimal


@dataclass
class BalanceChanged(TradingEvent):
    symbol: str
    currency: str
    balance: Decimal


@dataclass
class RiskStateChanged(TradingEvent):
    symbol: str
    drawdown: Decimal
