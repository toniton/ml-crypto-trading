from __future__ import annotations

from dataclasses import field
from datetime import datetime

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class MetricSample:
    metric_id: str
    timestamp: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)
