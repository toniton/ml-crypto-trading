from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from src.agent.runtime_debug.models import (
    DebugDiagnosis,
    DebugSuggestion,
    ErrorCategory,
    ErrorSeverity,
    IncidentStatus,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.database.dao.runtime_incident_dao import RuntimeErrorEventDao, RuntimeIncidentDao
from src.database.repositories.runtime_incident_repository import RuntimeIncidentRepository


class PostgresRuntimeIncidentRepository(RuntimeIncidentRepository):
    def save(self, entity: RuntimeIncident) -> RuntimeIncident:
        dao = self._to_incident_dao(entity)
        self.database_session.add(dao)
        self.database_session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[RuntimeIncident]:
        dao = (
            self.database_session.query(RuntimeIncidentDao)
            .filter(RuntimeIncidentDao.id == entity_id)
            .first()
        )
        return self._to_incident_model(dao) if dao else None

    def get_all(self) -> List[RuntimeIncident]:
        return self.list_incidents()

    def update(self, entity_id: str, entity: RuntimeIncident):
        dao = (
            self.database_session.query(RuntimeIncidentDao)
            .filter(RuntimeIncidentDao.id == entity_id)
            .first()
        )
        if not dao:
            return
        dao.status = entity.status.value
        dao.category = entity.category.value
        dao.severity = entity.severity.value
        dao.last_seen = entity.last_seen
        dao.occurrence_count = entity.occurrence_count
        dao.diagnosis = entity.diagnosis.to_dict() if entity.diagnosis else None
        dao.suggestion = entity.suggestion.to_dict() if entity.suggestion else None
        dao.notes = entity.notes
        self.database_session.flush()

    def upsert(self, entity: RuntimeIncident) -> None:
        existing = (
            self.database_session.query(RuntimeIncidentDao)
            .filter(RuntimeIncidentDao.id == str(entity.id))
            .first()
        )
        if existing:
            self.update(str(entity.id), entity)
        else:
            self.save(entity)

    def get_by_fingerprint(
            self,
            fingerprint: str,
            status_filter: Optional[List[IncidentStatus]] = None,
    ) -> Optional[RuntimeIncident]:
        query = self.database_session.query(RuntimeIncidentDao).filter(
            RuntimeIncidentDao.fingerprint == fingerprint
        )
        if status_filter:
            query = query.filter(
                RuntimeIncidentDao.status.in_([s.value for s in status_filter])
            )
        dao = query.order_by(RuntimeIncidentDao.last_seen.desc()).first()
        return self._to_incident_model(dao) if dao else None

    def list_incidents(
            self,
            status: Optional[IncidentStatus] = None,
            severity: Optional[ErrorSeverity] = None,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[RuntimeIncident]:
        query = self.database_session.query(RuntimeIncidentDao)
        if status:
            query = query.filter(RuntimeIncidentDao.status == status.value)
        if severity:
            query = query.filter(RuntimeIncidentDao.severity == severity.value)
        if asset:
            query = query.filter(RuntimeIncidentDao.asset == asset)
        if exchange:
            query = query.filter(RuntimeIncidentDao.exchange == exchange)

        rows = (
            query.order_by(RuntimeIncidentDao.last_seen.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_incident_model(r) for r in rows]

    def list_active_incidents(self) -> List[RuntimeIncident]:
        active_statuses = [
            IncidentStatus.DETECTED.value,
            IncidentStatus.INVESTIGATING.value,
            IncidentStatus.DIAGNOSED.value,
            IncidentStatus.SUGGESTION_READY.value,
            IncidentStatus.ACKNOWLEDGED.value,
        ]
        rows = (
            self.database_session.query(RuntimeIncidentDao)
            .filter(RuntimeIncidentDao.status.in_(active_statuses))
            .order_by(RuntimeIncidentDao.last_seen.desc())
            .all()
        )
        return [self._to_incident_model(r) for r in rows]

    def add_error_event(self, event: RuntimeErrorEvent) -> RuntimeErrorEvent:
        dao = self._to_error_event_dao(event)
        self.database_session.add(dao)
        self.database_session.flush()
        return event

    def get_error_events(self, incident_id: UUID, limit: int = 100) -> List[RuntimeErrorEvent]:
        rows = (
            self.database_session.query(RuntimeErrorEventDao)
            .filter(RuntimeErrorEventDao.incident_id == str(incident_id))
            .order_by(RuntimeErrorEventDao.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [self._to_error_event_model(r) for r in rows]

    def get_recent_error_events(
            self,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 20,
    ) -> List[RuntimeErrorEvent]:
        query = self.database_session.query(RuntimeErrorEventDao)
        if asset:
            query = query.filter(RuntimeErrorEventDao.asset == asset)
        if exchange:
            query = query.filter(RuntimeErrorEventDao.exchange == exchange)
        rows = query.order_by(RuntimeErrorEventDao.timestamp.desc()).limit(limit).all()
        return [self._to_error_event_model(r) for r in rows]

    def update_diagnosis(self, incident_id: UUID, diagnosis: DebugDiagnosis, confidence: str) -> None:
        self.database_session.query(RuntimeIncidentDao).filter(
            RuntimeIncidentDao.id == str(incident_id)
        ).update(
            {
                "diagnosis": diagnosis.to_dict(),
                "status": IncidentStatus.DIAGNOSED.value,
            }
        )
        self.database_session.flush()

    def update_suggestion(self, incident_id: UUID, suggestion: DebugSuggestion, status: IncidentStatus) -> None:
        self.database_session.query(RuntimeIncidentDao).filter(
            RuntimeIncidentDao.id == str(incident_id)
        ).update(
            {
                "suggestion": suggestion.to_dict(),
                "status": status.value,
            }
        )
        self.database_session.flush()

    def update_status(self, incident_id: UUID, status: IncidentStatus, notes: Optional[str] = None) -> None:
        values: dict[str, Any] = {"status": status.value}
        if notes is not None:
            values["notes"] = notes
        self.database_session.query(RuntimeIncidentDao).filter(
            RuntimeIncidentDao.id == str(incident_id)
        ).update(values)
        self.database_session.flush()

    @staticmethod
    def _to_incident_dao(model: RuntimeIncident) -> RuntimeIncidentDao:
        return RuntimeIncidentDao(
            id=str(model.id),
            fingerprint=model.fingerprint,
            status=model.status.value,
            category=model.category.value,
            severity=model.severity.value,
            component=model.component,
            operation=model.operation,
            asset=model.asset,
            exchange=model.exchange,
            commit_hash=model.commit_hash,
            first_seen=model.first_seen,
            last_seen=model.last_seen,
            occurrence_count=model.occurrence_count,
            diagnosis=model.diagnosis.to_dict() if model.diagnosis else None,
            suggestion=model.suggestion.to_dict() if model.suggestion else None,
            notes=model.notes,
        )

    @staticmethod
    def _to_incident_model(dao: RuntimeIncidentDao) -> RuntimeIncident:
        diag = DebugDiagnosis.from_dict(dao.diagnosis) if dao.diagnosis else None
        sugg = DebugSuggestion.from_dict(dao.suggestion) if dao.suggestion else None
        event_ids = [UUID(e.id) for e in dao.error_events] if dao.error_events else []

        return RuntimeIncident(
            id=UUID(dao.id),
            fingerprint=dao.fingerprint,
            status=IncidentStatus(dao.status),
            category=ErrorCategory(dao.category),
            severity=ErrorSeverity(dao.severity),
            component=dao.component,
            operation=dao.operation,
            asset=dao.asset,
            exchange=dao.exchange,
            commit_hash=dao.commit_hash,
            first_seen=dao.first_seen,
            last_seen=dao.last_seen,
            occurrence_count=dao.occurrence_count,
            error_events=event_ids,
            diagnosis=diag,
            suggestion=sugg,
            notes=dao.notes,
        )

    @staticmethod
    def _to_error_event_dao(model: RuntimeErrorEvent) -> RuntimeErrorEventDao:
        return RuntimeErrorEventDao(
            id=str(model.id),
            incident_id=str(model.incident_id) if model.incident_id else None,
            timestamp=model.timestamp,
            severity=model.severity.value,
            component=model.component,
            error_type=model.error_type,
            message=model.message,
            traceback=model.traceback,
            operation=model.operation,
            asset=model.asset,
            order_id=model.order_id,
            exchange=model.exchange,
            exchange_code=model.exchange_code,
            http_status=model.http_status,
            commit_hash=model.commit_hash,
            metadata_payload=model.metadata,
            fingerprint=model.fingerprint,
        )

    @staticmethod
    def _to_error_event_model(dao: RuntimeErrorEventDao) -> RuntimeErrorEvent:
        return RuntimeErrorEvent(
            id=UUID(dao.id),
            timestamp=dao.timestamp,
            severity=ErrorSeverity(dao.severity),
            component=dao.component,
            error_type=dao.error_type,
            message=dao.message,
            traceback=dao.traceback,
            operation=dao.operation,
            asset=dao.asset,
            order_id=dao.order_id,
            exchange=dao.exchange,
            exchange_code=dao.exchange_code,
            http_status=dao.http_status,
            commit_hash=dao.commit_hash,
            metadata=dao.metadata_payload or {},
            fingerprint=dao.fingerprint,
            incident_id=UUID(dao.incident_id) if dao.incident_id else None,
        )
