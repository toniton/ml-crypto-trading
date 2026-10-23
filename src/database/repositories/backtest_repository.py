from __future__ import annotations

import abc
from typing import Any, Optional

from src.backtest.domain.metrics import BacktestMetrics
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.database.repositories.base_repository import BaseRepository


class BacktestRepository(BaseRepository[BacktestSession]):

    @abc.abstractmethod
    def save_session(self, session: BacktestSession) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def update_session(self, session: BacktestSession) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_session(self, session_id: str) -> Optional[BacktestSession]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_sessions(self, limit: int = 50) -> list[BacktestSession]:
        raise NotImplementedError

    @abc.abstractmethod
    def save_result(self, result: BacktestResult, metrics: Optional[BacktestMetrics | dict[str, Any]] = None) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_result(self, session_id: str) -> Optional[BacktestResult]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_result_metrics(self, session_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def acquire_next_queued_session(self, worker_id: str, lease_duration_seconds: int) -> Optional[BacktestSession]:
        raise NotImplementedError

    @abc.abstractmethod
    def acquire_session(self, session_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def renew_lease(self, session_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_completed(
            self,
            session_id: str,
            result: BacktestResult,
            metrics: Optional[BacktestMetrics | dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_failed(self, session_id: str, error_message: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_cancelled(self, session_id: str, reason: Optional[str] = None) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def recover_abandoned_sessions(self, timeout_seconds: int) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def count_active_sessions(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def is_session_active(self, session_id: str) -> bool:
        raise NotImplementedError
