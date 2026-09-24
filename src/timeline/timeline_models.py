from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.events.decision_models import ArtifactRef, EntityRef


class TimelineCategory(str, Enum):
    TRADING = "TRADING"
    DECISION = "DECISION"
    AGENT = "AGENT"
    APPROVAL = "APPROVAL"
    VCS = "VCS"
    BACKTEST = "BACKTEST"
    RUNTIME = "RUNTIME"
    SYSTEM = "SYSTEM"


# pylint: disable=too-many-instance-attributes
@dataclass
class TimelineItem:
    timeline_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: TimelineCategory = TimelineCategory.TRADING
    severity: str = "INFO"
    title: str = ""
    summary: str = ""
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    actor_type: str = "SYSTEM"
    actor_id: Optional[str] = None
    primary_entity: Optional[EntityRef] = None
    entities: list[EntityRef] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeline_id": self.timeline_id,
            "timestamp": self.timestamp,
            "category": self.category.value if isinstance(self.category, TimelineCategory) else self.category,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "primary_entity": self.primary_entity.to_dict() if self.primary_entity else None,
            "entities": [e.to_dict() for e in self.entities],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata,
        }
