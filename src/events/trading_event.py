from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.core.interfaces.event import Event


@dataclass
class TradingEvent(Event):
    """Base class for live trading domain events.

    Concrete subclasses carry typed fields and identify themselves by their class
    name, mirroring the :class:`BacktestEvent` contract so that both live and
    backtest events can be consumed uniformly.
    """

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
