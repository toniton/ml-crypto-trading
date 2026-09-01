from __future__ import annotations

from dataclasses import field
from datetime import datetime, timezone
from uuid import uuid4

from pydantic.dataclasses import dataclass

from src.metrics.models.metric_type import AggregationType, MetricType


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    metric_type: MetricType = MetricType.COUNTER
    unit: str = ""
    description: str = ""
    aggregation: AggregationType | None = None
    retention_seconds: int = 30 * 24 * 3600
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
