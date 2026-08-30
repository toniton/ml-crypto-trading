from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from api.interfaces.backtest_request import BacktestRequest
from src.backtest.domain.result import BacktestResult


class BacktestSessionStatus(str, Enum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def generate_session_id() -> str:
    return f"bt_{uuid4().hex}"


class BacktestSession(BaseModel):
    id: str = Field(default_factory=generate_session_id)
    asset: str
    request: BacktestRequest
    status: BacktestSessionStatus = BacktestSessionStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: Optional[BacktestResult] = None

    def initialize(self) -> None:
        self.status = BacktestSessionStatus.INITIALIZING

    def start(self) -> None:
        self.status = BacktestSessionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def complete(self, result: Optional[BacktestResult] = None) -> None:
        self.status = BacktestSessionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        if result is not None:
            self.result = result

    def attach_result(self, result: BacktestResult) -> None:
        self.result = result

    def fail(self, error: str) -> None:
        self.status = BacktestSessionStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error

    def cancel(self) -> None:
        self.status = BacktestSessionStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
