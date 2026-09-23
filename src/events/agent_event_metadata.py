from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class AgentEventMetadata:
    request_id: UUID | None = None
    correlation_id: UUID = field(default_factory=uuid4)
    causation_id: UUID | None = None
    sequence_number: int = 0
