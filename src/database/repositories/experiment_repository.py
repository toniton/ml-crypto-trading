from __future__ import annotations

import abc
from typing import Any, Optional

from src.database.dao.experiment_dao import ExperimentDao
from src.database.repositories.base_repository import BaseRepository


class ExperimentRepository(BaseRepository[ExperimentDao]):

    @abc.abstractmethod
    def save_experiment(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            experiment_id: str,
            name: str,
            ticker_symbol: str,
            branch_id: str,
            base_commit_hash: str,
            status: str,
            spec: dict[str, Any],
            run_bindings: list[dict[str, Any]],
            report: Optional[dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_experiments(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def update_status(
            self,
            experiment_id: str,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def update_bindings(
            self,
            experiment_id: str,
            run_bindings: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def update_report(
            self,
            experiment_id: str,
            status: str,
            report: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_experiment(self, experiment_id: str) -> bool:
        raise NotImplementedError
