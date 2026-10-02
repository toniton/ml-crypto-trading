from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from src.agent.oracle.oracle_summary import OracleSummary
from src.backtest.events import (
    BalanceUpdateEvent,
    PortfolioSnapshotEvent,
)
from src.core.interfaces.event import Event
from src.trading.events import (
    BalanceChangedEvent,
    MarketDataEvent,
    MarketStateChangedEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
    RiskStateChangedEvent,
)

LIVE_EVENT_CLASSES = (
    OrderSubmittedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    PositionChangedEvent,
    BalanceChangedEvent,
    MarketStateChangedEvent,
    RiskStateChangedEvent,
)

BACKTEST_EVENT_CLASSES = (
    OrderSubmittedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    BalanceUpdateEvent,
    PortfolioSnapshotEvent,
    MarketDataEvent,
)

LIVE_EVENT_TYPES = tuple(cls.__name__ for cls in LIVE_EVENT_CLASSES)
BACKTEST_EVENT_TYPES = tuple(cls.__name__ for cls in BACKTEST_EVENT_CLASSES)
ORACLE_EVENT_TYPES = tuple(dict.fromkeys(LIVE_EVENT_TYPES + BACKTEST_EVENT_TYPES))


class OracleSummaryEvent(Event):
    """An application event carrying a freshly generated :class:`OracleSummary`."""

    def __init__(
            self,
            summary: OracleSummary,
            *,
            event_id: Optional[str] = None,
            timestamp: Optional[str] = None,
            metadata: Optional[dict] = None,
    ) -> None:
        self._summary = summary
        self._id = event_id or uuid.uuid4().hex
        self._timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self._metadata = dict(metadata or {})

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return type(self).__name__

    @property
    def payload(self) -> OracleSummary:
        return self._summary

    @property
    def metadata(self) -> dict:
        return self._metadata

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def summary(self) -> str:
        return self._summary.summary

    @property
    def market_state(self) -> str:
        return self._summary.market_state

    @property
    def trading_state(self) -> str:
        return self._summary.trading_state

    @property
    def risk_state(self) -> str:
        return self._summary.risk_state

    @property
    def symbol(self) -> Optional[str]:
        return self._summary.symbol

    @property
    def session_id(self) -> Optional[str]:
        return self._summary.session_id

    @property
    def correlation_id(self) -> str:
        return self._summary.correlation_id

    @property
    def observations(self) -> tuple[str, ...]:
        return self._summary.observations

    @property
    def recommendations(self) -> tuple[str, ...]:
        return self._summary.recommendations

    @property
    def model(self) -> Optional[str]:
        return self._summary.model

    @property
    def model_version(self) -> Optional[str]:
        return self._summary.model_version

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self._summary.to_dict(),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


ORACLE_SUMMARY_EVENT_TYPE = OracleSummaryEvent.__name__
