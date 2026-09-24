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
class StrategyEvaluatedEvent(TradingEvent):
    symbol: str
    evaluated_at: float


@dataclass
class SignalGeneratedEvent(TradingEvent):
    symbol: str
    action: str
    generated_at: float


@dataclass
class MarketStateChangedEvent(TradingEvent):
    symbol: str
    price: Decimal
    market_timestamp: float


@dataclass
class OrderSubmittedEvent(TradingEvent):
    symbol: str
    order: Order


@dataclass
class OrderFilledEvent(TradingEvent):
    symbol: str
    order: Order


@dataclass
class OrderCancelledEvent(TradingEvent):
    symbol: str
    order: Order


@dataclass
class OrderRejectedEvent(TradingEvent):
    symbol: str
    order: Order
    reason: str = ""


@dataclass
class PositionChangedEvent(TradingEvent):
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal
    position_qty: Decimal
    realized_pnl: Decimal


@dataclass
class BalanceChangedEvent(TradingEvent):
    symbol: str
    currency: str
    balance: Decimal


@dataclass
class RiskStateChangedEvent(TradingEvent):
    symbol: str
    drawdown: Decimal


@dataclass
class ConsensusEvaluatedEvent(TradingEvent):
    symbol: str
    decision: str = "HOLD"
    buy_votes: int = 0
    sell_votes: int = 0
    total_strategies: int = 0
    quorum_met: bool = False
    evaluated_at: float = 0.0
    factors: dict = None

