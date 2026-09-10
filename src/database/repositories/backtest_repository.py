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
