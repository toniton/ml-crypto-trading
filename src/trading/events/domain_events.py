from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.events.trading_event import TradingEvent


@dataclass
class MarketDataEvent(TradingEvent):
    ticker_symbol: str
    market_data: MarketData

    def _resolve_asset(self) -> Optional[str]:
        return self.ticker_symbol


@dataclass
class StrategyEvaluatedEvent(TradingEvent):
    symbol: str
    evaluated_at: float

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class SignalGeneratedEvent(TradingEvent):
    symbol: str
    action: str
    generated_at: float

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class MarketStateChangedEvent(TradingEvent):
    symbol: str
    price: Decimal
    market_timestamp: float

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class OrderSubmittedEvent(TradingEvent):
    symbol: str
    order: Order

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class OrderFilledEvent(TradingEvent):
    symbol: str
    order: Order

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class OrderCancelledEvent(TradingEvent):
    symbol: str
    order: Order

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class OrderRejectedEvent(TradingEvent):
    symbol: str
    order: Order
    reason: str = ""

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class PositionChangedEvent(TradingEvent):
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal
    position_qty: Decimal
    realized_pnl: Decimal

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class BalanceChangedEvent(TradingEvent):
    symbol: str
    currency: str
    balance: Decimal

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class RiskStateChangedEvent(TradingEvent):
    symbol: str
    drawdown: Decimal

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


@dataclass
class ConsensusEvaluatedEvent(TradingEvent):
    symbol: str
    decision: str = "HOLD"
    buy_votes: int = 0
    sell_votes: int = 0
    total_strategies: int = 0
    quorum_met: bool = False
    evaluated_at: float = 0.0
    factors: Optional[dict] = None

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol
