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
