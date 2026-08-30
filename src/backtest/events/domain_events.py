from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.backtest.domain.result import MarketDataPoint, PortfolioSnapshot
from src.backtest.execution.execution_types import ExecutionResult
from src.core.interfaces.event import Event


@dataclass
class BacktestEvent(Event):
    def __post_init__(self) -> None:
        self._id: str = uuid4().hex
        self._event_type: str = type(self).__name__
        self._payload: dict = asdict(self)
        self._timestamp: str = datetime.now(timezone.utc).isoformat()
        self._metadata: dict = {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return self._event_type

    @property
    def payload(self) -> dict:
        return self._payload

    @property
    def metadata(self) -> dict:
        return self._metadata

    @property
    def timestamp(self) -> str:
        return self._timestamp

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class TickEvent(BacktestEvent):
    tick_time: int


@dataclass
class MarketDataEvent(BacktestEvent):
    market_data: MarketData
    ticker_symbol: str


@dataclass
class MarketDataPointEvent(BacktestEvent):
    point: MarketDataPoint
    ticker_symbol: str


@dataclass
class CandlesEvent(BacktestEvent):
    candles: list[Candle]
    ticker_symbol: str


@dataclass
class OrderSubmittedEvent(BacktestEvent):
    order: Order


@dataclass
class OrderFilledEvent(BacktestEvent):
    order: Order
    execution: Optional[ExecutionResult] = None


# Backward-compatible alias
OrderFillEvent = OrderFilledEvent


@dataclass
class OrderCancelledEvent(BacktestEvent):
    order: Order


@dataclass
class PortfolioSnapshotEvent(BacktestEvent):
    snapshot: PortfolioSnapshot
    ticker_symbol: str


@dataclass
class BalanceUpdateEvent(BacktestEvent):
    balances: list[AccountBalance]
