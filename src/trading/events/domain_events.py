from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade import Trade
from src.events.trading_event import TradingEvent


class DecisionRejectedReason(str, Enum):
    NO_QUORUM = "NO_QUORUM"
    GUARD_HALT = "GUARD_HALT"
    RISK_REJECTED = "RISK_REJECTED"
    BELOW_MIN_QUANTITY = "BELOW_MIN_QUANTITY"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    NEGATIVE_EDGE = "NEGATIVE_EDGE"
    OUTSTANDING_INTENT = "OUTSTANDING_INTENT"
    QUANTITY_CALCULATION_FAILED = "QUANTITY_CALCULATION_FAILED"


@dataclass
class DecisionRejectedEvent(TradingEvent):
    EVENT_TYPE = "DecisionRejectedEvent"
    symbol: str = ""
    action: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol


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


@dataclass
class TradeClosedEvent(TradingEvent):
    symbol: str
    trade: Trade

    def _resolve_asset(self) -> Optional[str]:
        return self.symbol
