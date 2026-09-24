from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.core.interfaces.event import Event


@dataclass(frozen=True)
class RefChangedEvent(Event):
    ref: str
    commit_hash: str

    @property
    def id(self) -> str:
        return uuid4().hex

    @property
    def type(self) -> str:
        return "RefChangedEvent"

    @property
    def payload(self) -> dict:
        return {"ref": self.ref, "commit_hash": self.commit_hash}

    @property
    def metadata(self) -> dict:
        return {}

    @property
    def timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
