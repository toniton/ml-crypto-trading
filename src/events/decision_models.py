from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.events.trading_event import TradingEvent


class ActorType(str, Enum):
    SYSTEM = "SYSTEM"
    WATCHDOG = "WATCHDOG"
    AGENT = "AGENT"
    USER = "USER"
    EXCHANGE = "EXCHANGE"


class DecisionType(str, Enum):
    CONSENSUS_VOTE = "CONSENSUS_VOTE"
    INVESTIGATION_OUTCOME = "INVESTIGATION_OUTCOME"
    PROPOSAL_APPROVAL = "PROPOSAL_APPROVAL"
    RISK_GATE_DECISION = "RISK_GATE_DECISION"


@dataclass
class EntityRef:
    type: str
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}


@dataclass
class ArtifactRef:
    type: str
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}


@dataclass
class DecisionRecord:
    decision_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actor_type: ActorType = ActorType.AGENT
    actor_id: Optional[str] = None
    decision_type: DecisionType = DecisionType.INVESTIGATION_OUTCOME
    summary: str = ""
    rationale: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    entities: list[EntityRef] = field(default_factory=list)
    proposed_action_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        actor_type_val = self.actor_type.value if isinstance(self.actor_type, ActorType) else self.actor_type
        decision_type_val = (
            self.decision_type.value if isinstance(self.decision_type, DecisionType) else self.decision_type
        )
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "actor_type": actor_type_val,
            "actor_id": self.actor_id,
            "decision_type": decision_type_val,
            "summary": self.summary,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
            "entities": [e.to_dict() for e in self.entities],
            "proposed_action_id": self.proposed_action_id,
        }


@dataclass
class AgentDecisionRecordedEvent(TradingEvent):
    EVENT_TYPE = "AgentDecisionRecordedEvent"
    decision: DecisionRecord = field(default_factory=DecisionRecord)
