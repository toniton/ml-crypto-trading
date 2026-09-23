from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from src.events.agent_event_metadata import AgentEventMetadata
from src.events.trading_event import TradingEvent


@dataclass
class AgentEvent(TradingEvent):
    agent_metadata: AgentEventMetadata = field(default_factory=AgentEventMetadata)

    @property
    def event_id(self) -> str:
        return self._id

    @property
    def request_id(self) -> UUID | None:
        return self.agent_metadata.request_id

    @property
    def correlation_id(self) -> UUID:
        return self.agent_metadata.correlation_id

    @property
    def causation_id(self) -> UUID | None:
        return self.agent_metadata.causation_id

    @property
    def sequence_number(self) -> int:
        return self.agent_metadata.sequence_number