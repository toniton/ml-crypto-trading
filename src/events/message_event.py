from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar

from src.core.interfaces.event import Event

T = TypeVar("T")


class MessageEvent(Event[T]):
    def __init__(
            self,
            event_type: str,
            payload: T,
            *,
            event_id: Optional[str] = None,
            timestamp: Optional[str] = None,
            metadata: Optional[dict] = None,
    ) -> None:
        self._id = event_id or uuid.uuid4().hex
        self._event_type = event_type
        self._payload = payload
        self._timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self._metadata = dict(metadata or {})

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return self._event_type

    @property
    def payload(self) -> T:
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
            "payload": self._serialize_payload(self.payload),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @staticmethod
    def _serialize_payload(payload: Any) -> Any:
        if payload is None:
            return None
        if hasattr(payload, "to_dict"):
            return payload.to_dict()
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return payload
        return str(payload)
