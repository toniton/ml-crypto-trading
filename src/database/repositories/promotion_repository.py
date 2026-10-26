from __future__ import annotations

import abc
from typing import Any, Optional

from src.database.dao.promotion_audit_event_dao import PromotionAuditEventDao
from src.database.dao.promotion_record_dao import PromotionRecordDao
from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.base_repository import BaseRepository


class SimulatedRunRepository(BaseRepository[SimulatedRunDao]):

    @abc.abstractmethod
    def save_run(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            run_id: str,
            experiment_id: str,
            candidate_id: str,
            candidate_commit: str,
            config_hash: str,
            status: str,
            market_data_spec: dict[str, Any],
            execution_spec: dict[str, Any],
            error_message: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_runs(
            self,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def update_status(
            self,
            run_id: str,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        raise NotImplementedError


class SimulationReportRepository(BaseRepository[SimulationReportDao]):

    @abc.abstractmethod
    def save_report(
            self,
            report_id: str,
            run_id: str,
            config_hash: str,
            decision: str,
            summary_metrics: dict[str, Any],
            report_payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_report_by_run(self, run_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class PromotionRecordRepository(BaseRepository[PromotionRecordDao]):

    @abc.abstractmethod
    def save_promotion(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            promotion_id: str,
            idempotency_key: str,
            experiment_id: str,
            candidate_id: str,
            source_commit: str,
            target_ref: str,
            status: str,
            approver: str,
            gate_results: dict[str, Any],
            approval_notes: Optional[str] = None,
            merge_commit_hash: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_promotion(self, promotion_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_promotions(
            self,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class PromotionAuditRepository(BaseRepository[PromotionAuditEventDao]):

    @abc.abstractmethod
    def record_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            event_id: str,
            event_type: str,
            to_state: str,
            actor: str,
            payload: dict[str, Any],
            promotion_id: Optional[str] = None,
            from_state: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def list_events(
            self,
            promotion_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
