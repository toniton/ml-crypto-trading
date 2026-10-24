from __future__ import annotations

import abc
from typing import Any, Optional

from src.database.dao.walk_forward_dao import WalkForwardRunDao
from src.database.repositories.base_repository import BaseRepository


class WalkForwardRepository(BaseRepository[WalkForwardRunDao]):

    @abc.abstractmethod
    def save_run(
            self,
            run_id: str,
            ticker_symbol: str,
            status: str,
            spec: dict[str, Any],
            summary: Optional[dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def update_run_summary(
            self,
            run_id: str,
            status: str,
            summary: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def acquire_next_queued_run(self, worker_id: str, lease_duration_seconds: int) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def acquire_run(self, run_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def renew_lease(self, run_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_completed(self, run_id: str, summary: dict[str, Any]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_failed(self, run_id: str, error_message: str, summary: Optional[dict[str, Any]] = None) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def mark_cancelled(self, run_id: str, reason: Optional[str] = None) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def recover_abandoned_runs(self, timeout_seconds: int) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def count_active_runs(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def is_run_active(self, run_id: str) -> bool:
        raise NotImplementedError
