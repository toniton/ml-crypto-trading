from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from src.core.interfaces.event import Event


@dataclass
class TradingEvent(Event):
    """Base class for live trading domain events with causal lineage tracking."""

    def __post_init__(self) -> None:
        self._id: str = getattr(self, "_id", None) or uuid4().hex
        self._event_type: str = getattr(self, "EVENT_TYPE", None) or type(self).__name__
        self._timestamp: str = getattr(self, "_timestamp", None) or datetime.now(timezone.utc).isoformat()
        self._correlation_id: Optional[str] = getattr(self, "_correlation_id", None)
        self._causation_id: Optional[str] = getattr(self, "_causation_id", None)
        self._source: str = getattr(self, "_source", "trading_engine")
        self._actor_type: str = getattr(self, "_actor_type", "SYSTEM")
        self._actor_id: Optional[str] = getattr(self, "_actor_id", None)
        self._commit_hash: Optional[str] = getattr(self, "_commit_hash", None)
        self._asset: Optional[str] = getattr(self, "symbol", None) or getattr(self, "ticker_symbol", None) or getattr(self, "_asset", None)
        self._exchange: Optional[str] = getattr(self, "_exchange", None)
        self._metadata: dict = getattr(self, "_metadata", {})
        self._payload: dict = asdict(self)

    @property
    def id(self) -> str:
        return self._id

    @property
    def event_id(self) -> str:
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

    @property
    def correlation_id(self) -> Optional[str]:
        return self._correlation_id

    @correlation_id.setter
    def correlation_id(self, val: Optional[str]) -> None:
        self._correlation_id = val

    @property
    def causation_id(self) -> Optional[str]:
        return self._causation_id

    @causation_id.setter
    def causation_id(self, val: Optional[str]) -> None:
        self._causation_id = val

    @property
    def source(self) -> str:
        return self._source

    @source.setter
    def source(self, val: str) -> None:
        self._source = val

    @property
    def actor_type(self) -> str:
        return self._actor_type

    @actor_type.setter
    def actor_type(self, val: str) -> None:
        self._actor_type = val

    @property
    def actor_id(self) -> Optional[str]:
        return self._actor_id

    @actor_id.setter
    def actor_id(self, val: Optional[str]) -> None:
        self._actor_id = val

    @property
    def commit_hash(self) -> Optional[str]:
        return self._commit_hash

    @commit_hash.setter
    def commit_hash(self, val: Optional[str]) -> None:
        self._commit_hash = val

    @property
    def asset(self) -> Optional[str]:
        return self._asset or getattr(self, "symbol", None) or getattr(self, "ticker_symbol", None)

    @asset.setter
    def asset(self, val: Optional[str]) -> None:
        self._asset = val

    @property
    def exchange(self) -> Optional[str]:
        return self._exchange

    @exchange.setter
    def exchange(self, val: Optional[str]) -> None:
        self._exchange = val

    def set_causality(
            self,
            *,
            correlation_id: Optional[str] = None,
            causation_id: Optional[str] = None,
            source: Optional[str] = None,
            actor_type: Optional[str] = None,
            actor_id: Optional[str] = None,
            commit_hash: Optional[str] = None,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
    ) -> TradingEvent:
        if correlation_id is not None:
            self._correlation_id = correlation_id
        if causation_id is not None:
            self._causation_id = causation_id
        if source is not None:
            self._source = source
        if actor_type is not None:
            self._actor_type = actor_type
        if actor_id is not None:
            self._actor_id = actor_id
        if commit_hash is not None:
            self._commit_hash = commit_hash
        if asset is not None:
            self._asset = asset
        if exchange is not None:
            self._exchange = exchange
        return self

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "type": self.type,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "source": self.source,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "commit_hash": self.commit_hash,
            "asset": self.asset,
            "exchange": self.exchange,
        }
