from __future__ import annotations

from datetime import datetime, timedelta

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class RetentionPolicy:
    duration: timedelta
    cleanup_interval: timedelta = timedelta(hours=1)
    batch_size: int = 10000
    enabled: bool = True


@dataclass(frozen=True)
class RetentionResult:
    deleted_samples: int
    started_at: datetime
    completed_at: datetime
