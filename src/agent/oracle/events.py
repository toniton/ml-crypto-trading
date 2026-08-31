from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from src.agent.oracle.oracle_summary import OracleSummary
from src.core.interfaces.event import Event
from src.trading.events import (
    BalanceChanged,
    MarketStateChanged,
    OrderCancelled,
    OrderExecuted,
    OrderSubmitted,
    PositionChanged,
    RiskStateChanged,
)

ORACLE_SUMMARY_EVENT_TYPE = "OracleSummaryEvent"

LIVE_EVENT_TYPES = tuple(
    event_class.__name__
    for event_class in (
        OrderSubmitted,
        OrderExecuted,
        OrderCancelled,
        PositionChanged,
        BalanceChanged,
        MarketStateChanged,
        RiskStateChanged,
    )
)

BACKTEST_EVENT_TYPES = (
    "OrderSubmittedEvent",
    "OrderFilledEvent",
    "OrderCancelledEvent",
    "BalanceUpdateEvent",
    "PortfolioSnapshotEvent",
    "MarketDataEvent",
)

ORACLE_EVENT_TYPES = LIVE_EVENT_TYPES + BACKTEST_EVENT_TYPES


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
        return ORACLE_SUMMARY_EVENT_TYPE

    @property
    def payload(self) -> OracleSummary:
        return self._summary

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
            "payload": self._summary.to_dict(),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
