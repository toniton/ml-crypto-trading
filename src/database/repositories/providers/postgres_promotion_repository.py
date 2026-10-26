from __future__ import annotations

from typing import Any, List, Optional, cast

from src.database.dao.promotion_audit_event_dao import PromotionAuditEventDao
from src.database.dao.promotion_record_dao import PromotionRecordDao
from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.promotion_repository import (
    PromotionAuditRepository,
    PromotionRecordRepository,
    SimulatedRunRepository,
    SimulationReportRepository,
)


class PostgresSimulatedRunRepository(SimulatedRunRepository):

    def save(self, entity: SimulatedRunDao) -> SimulatedRunDao:
        self.save_run(
            run_id=entity.id,
            experiment_id=entity.experiment_id,
            candidate_id=entity.candidate_id,
            candidate_commit=entity.candidate_commit,
            config_hash=entity.config_hash,
            status=entity.status,
            market_data_spec=entity.market_data_spec or {},
            execution_spec=entity.execution_spec or {},
            error_message=entity.error_message,
        )
        return entity

    def get(self, entity_id: str) -> Optional[SimulatedRunDao]:
        row = (
            self.database_session.query(SimulatedRunDao)
            .filter(SimulatedRunDao.id == entity_id)
            .first()
        )
        return cast(Optional[SimulatedRunDao], row)

    def get_all(self) -> List[SimulatedRunDao]:
        rows = (
            self.database_session.query(SimulatedRunDao)
            .order_by(SimulatedRunDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[SimulatedRunDao], rows)

    def update(self, entity_id: str, entity: SimulatedRunDao) -> None:
        self.save(entity)

    def upsert(self, entity: SimulatedRunDao) -> None:
        self.save(entity)

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
        existing = (
            self.database_session.query(SimulatedRunDao)
            .filter(SimulatedRunDao.id == run_id)
            .first()
        )
        if existing:
            existing.experiment_id = experiment_id
            existing.candidate_id = candidate_id
            existing.candidate_commit = candidate_commit
            existing.config_hash = config_hash
            existing.status = status
            existing.market_data_spec = market_data_spec
            existing.execution_spec = execution_spec
            existing.error_message = error_message
        else:
            self.database_session.add(
                SimulatedRunDao(
                    id=run_id,
                    experiment_id=experiment_id,
                    candidate_id=candidate_id,
                    candidate_commit=candidate_commit,
                    config_hash=config_hash,
                    status=status,
                    market_data_spec=market_data_spec,
                    execution_spec=execution_spec,
                    error_message=error_message,
                )
            )
        self.database_session.flush()

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(SimulatedRunDao)
            .filter(SimulatedRunDao.id == run_id)
            .first()
        )
        return self._to_dict(row) if row else None

    def list_runs(
            self,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = self.database_session.query(SimulatedRunDao)
        if experiment_id:
            query = query.filter(SimulatedRunDao.experiment_id == experiment_id)
        if candidate_id:
            query = query.filter(SimulatedRunDao.candidate_id == candidate_id)
        if status:
            query = query.filter(SimulatedRunDao.status == status)

        rows = (
            query.order_by(SimulatedRunDao.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def update_status(
            self,
            run_id: str,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        row = (
            self.database_session.query(SimulatedRunDao)
            .filter(SimulatedRunDao.id == run_id)
            .first()
        )
        if row:
            row.status = status
            if error_message is not None:
                row.error_message = error_message
            self.database_session.flush()

    @staticmethod
    def _to_dict(row: SimulatedRunDao) -> dict[str, Any]:
        return {
            "run_id": row.id,
            "id": row.id,
            "experiment_id": row.experiment_id,
            "candidate_id": row.candidate_id,
            "candidate_commit": row.candidate_commit,
            "config_hash": row.config_hash,
            "status": row.status,
            "market_data_spec": row.market_data_spec or {},
            "execution_spec": row.execution_spec or {},
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


class PostgresSimulationReportRepository(SimulationReportRepository):

    def save(self, entity: SimulationReportDao) -> SimulationReportDao:
        self.save_report(
            report_id=entity.id,
            run_id=entity.run_id,
            config_hash=entity.config_hash,
            decision=entity.decision,
            summary_metrics=entity.summary_metrics or {},
            report_payload=entity.report_payload or {},
        )
        return entity

    def get(self, entity_id: str) -> Optional[SimulationReportDao]:
        row = (
            self.database_session.query(SimulationReportDao)
            .filter(SimulationReportDao.id == entity_id)
            .first()
        )
        return cast(Optional[SimulationReportDao], row)

    def get_all(self) -> List[SimulationReportDao]:
        rows = (
            self.database_session.query(SimulationReportDao)
            .order_by(SimulationReportDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[SimulationReportDao], rows)

    def update(self, entity_id: str, entity: SimulationReportDao) -> None:
        self.save(entity)

    def upsert(self, entity: SimulationReportDao) -> None:
        self.save(entity)

    def save_report(
            self,
            report_id: str,
            run_id: str,
            config_hash: str,
            decision: str,
            summary_metrics: dict[str, Any],
            report_payload: dict[str, Any],
    ) -> None:
        existing = (
            self.database_session.query(SimulationReportDao)
            .filter(SimulationReportDao.run_id == run_id)
            .first()
        )
        if existing:
            existing.config_hash = config_hash
            existing.decision = decision
            existing.summary_metrics = summary_metrics
            existing.report_payload = report_payload
        else:
            self.database_session.add(
                SimulationReportDao(
                    id=report_id,
                    run_id=run_id,
                    config_hash=config_hash,
                    decision=decision,
                    summary_metrics=summary_metrics,
                    report_payload=report_payload,
                )
            )
        self.database_session.flush()

    def get_report_by_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(SimulationReportDao)
            .filter(SimulationReportDao.run_id == run_id)
            .first()
        )
        return self._to_dict(row) if row else None

    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(SimulationReportDao)
            .filter(SimulationReportDao.id == report_id)
            .first()
        )
        return self._to_dict(row) if row else None

    @staticmethod
    def _to_dict(row: SimulationReportDao) -> dict[str, Any]:
        return {
            "report_id": row.id,
            "id": row.id,
            "run_id": row.run_id,
            "config_hash": row.config_hash,
            "decision": row.decision,
            "summary_metrics": row.summary_metrics or {},
            "report_payload": row.report_payload or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


class PostgresPromotionRecordRepository(PromotionRecordRepository):

    def save(self, entity: PromotionRecordDao) -> PromotionRecordDao:
        self.save_promotion(
            promotion_id=entity.id,
            idempotency_key=entity.idempotency_key,
            experiment_id=entity.experiment_id,
            candidate_id=entity.candidate_id,
            source_commit=entity.source_commit,
            target_ref=entity.target_ref,
            status=entity.status,
            approver=entity.approver,
            gate_results=entity.gate_results or {},
            approval_notes=entity.approval_notes,
            merge_commit_hash=entity.merge_commit_hash,
        )
        return entity

    def get(self, entity_id: str) -> Optional[PromotionRecordDao]:
        row = (
            self.database_session.query(PromotionRecordDao)
            .filter(PromotionRecordDao.id == entity_id)
            .first()
        )
        return cast(Optional[PromotionRecordDao], row)

    def get_all(self) -> List[PromotionRecordDao]:
        rows = (
            self.database_session.query(PromotionRecordDao)
            .order_by(PromotionRecordDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[PromotionRecordDao], rows)

    def update(self, entity_id: str, entity: PromotionRecordDao) -> None:
        self.save(entity)

    def upsert(self, entity: PromotionRecordDao) -> None:
        self.save(entity)

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
        existing = (
            self.database_session.query(PromotionRecordDao)
            .filter(PromotionRecordDao.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            existing.status = status
            existing.approver = approver
            existing.approval_notes = approval_notes
            existing.gate_results = gate_results
            if merge_commit_hash:
                existing.merge_commit_hash = merge_commit_hash
        else:
            self.database_session.add(
                PromotionRecordDao(
                    id=promotion_id,
                    idempotency_key=idempotency_key,
                    experiment_id=experiment_id,
                    candidate_id=candidate_id,
                    source_commit=source_commit,
                    target_ref=target_ref,
                    merge_commit_hash=merge_commit_hash,
                    status=status,
                    approver=approver,
                    approval_notes=approval_notes,
                    gate_results=gate_results,
                )
            )
        self.database_session.flush()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(PromotionRecordDao)
            .filter(PromotionRecordDao.idempotency_key == idempotency_key)
            .first()
        )
        return self._to_dict(row) if row else None

    def get_promotion(self, promotion_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(PromotionRecordDao)
            .filter(PromotionRecordDao.id == promotion_id)
            .first()
        )
        return self._to_dict(row) if row else None

    def list_promotions(
            self,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = self.database_session.query(PromotionRecordDao)
        if experiment_id:
            query = query.filter(PromotionRecordDao.experiment_id == experiment_id)
        if candidate_id:
            query = query.filter(PromotionRecordDao.candidate_id == candidate_id)

        rows = (
            query.order_by(PromotionRecordDao.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: PromotionRecordDao) -> dict[str, Any]:
        return {
            "promotion_id": row.id,
            "id": row.id,
            "idempotency_key": row.idempotency_key,
            "experiment_id": row.experiment_id,
            "candidate_id": row.candidate_id,
            "source_commit": row.source_commit,
            "target_ref": row.target_ref,
            "merge_commit_hash": row.merge_commit_hash,
            "status": row.status,
            "approver": row.approver,
            "approval_notes": row.approval_notes,
            "gate_results": row.gate_results or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


class PostgresPromotionAuditRepository(PromotionAuditRepository):

    def save(self, entity: PromotionAuditEventDao) -> PromotionAuditEventDao:
        self.record_event(
            event_id=entity.id,
            event_type=entity.event_type,
            to_state=entity.to_state,
            actor=entity.actor,
            payload=entity.payload or {},
            promotion_id=entity.promotion_id,
            from_state=entity.from_state,
        )
        return entity

    def get(self, entity_id: str) -> Optional[PromotionAuditEventDao]:
        row = (
            self.database_session.query(PromotionAuditEventDao)
            .filter(PromotionAuditEventDao.id == entity_id)
            .first()
        )
        return cast(Optional[PromotionAuditEventDao], row)

    def get_all(self) -> List[PromotionAuditEventDao]:
        rows = (
            self.database_session.query(PromotionAuditEventDao)
            .order_by(PromotionAuditEventDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[PromotionAuditEventDao], rows)

    def update(self, entity_id: str, entity: PromotionAuditEventDao) -> None:
        self.save(entity)

    def upsert(self, entity: PromotionAuditEventDao) -> None:
        self.save(entity)

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
        self.database_session.add(
            PromotionAuditEventDao(
                id=event_id,
                promotion_id=promotion_id,
                event_type=event_type,
                from_state=from_state,
                to_state=to_state,
                actor=actor,
                payload=payload,
            )
        )
        self.database_session.flush()

    def list_events(
            self,
            promotion_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = self.database_session.query(PromotionAuditEventDao)
        if promotion_id:
            query = query.filter(PromotionAuditEventDao.promotion_id == promotion_id)

        rows = (
            query.order_by(PromotionAuditEventDao.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: PromotionAuditEventDao) -> dict[str, Any]:
        return {
            "event_id": row.id,
            "id": row.id,
            "promotion_id": row.promotion_id,
            "event_type": row.event_type,
            "from_state": row.from_state,
            "to_state": row.to_state,
            "actor": row.actor,
            "payload": row.payload or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
