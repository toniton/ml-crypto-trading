from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.events.agent_event_metadata import AgentEventMetadata
from src.events.trading_event import TradingEvent


@dataclass
class AgentEvent(TradingEvent):
    agent_metadata: AgentEventMetadata = field(default_factory=AgentEventMetadata)

    def __init__(self):
        super().__init__()
        self._causation_id = None
        self._correlation_id = None

    @property
    def event_id(self) -> str:
        return self._id

    @property
    def request_id(self) -> UUID | None:
        return self.agent_metadata.request_id

    @property
    def correlation_id(self) -> UUID | str:
        if self._correlation_id is not None:
            return self._correlation_id
        return self.agent_metadata.correlation_id

    @correlation_id.setter
    def correlation_id(self, val: Any) -> None:
        self._correlation_id = str(val) if val is not None else None

    @property
    def causation_id(self) -> UUID | str | None:
        if self._causation_id is not None:
            return self._causation_id
        return self.agent_metadata.causation_id

    @causation_id.setter
    def causation_id(self, val: Any) -> None:
        self._causation_id = str(val) if val is not None else None

    @property
    def sequence_number(self) -> int:
        return self.agent_metadata.sequence_number

    def to_dict(self) -> dict:
        data = super().to_dict()
        if "agent_metadata" in data.get("payload", {}):
            meta = data["payload"]["agent_metadata"]
            if isinstance(meta, dict):
                for key in ("request_id", "correlation_id", "causation_id"):
                    if meta.get(key) is not None:
                        meta[key] = str(meta[key])
        return data
