from __future__ import annotations

from datetime import datetime

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class MetricPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class MetricSeries:
    name: str
    unit: str
    interval_seconds: int
    start_time: datetime
    end_time: datetime
    points: tuple[MetricPoint, ...]
