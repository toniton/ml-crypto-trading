from __future__ import annotations

from dataclasses import field
from datetime import datetime
from typing import Optional

from pydantic.dataclasses import dataclass

from src.metrics.models.metric_type import AggregationType


@dataclass(frozen=True)
class MetricQuery:
    metric_names: tuple[str, ...]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    interval_seconds: int = 60
    aggregation: Optional[AggregationType] = None
    labels: dict[str, str] = field(default_factory=dict)
