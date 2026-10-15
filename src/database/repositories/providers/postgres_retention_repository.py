from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from src.database.dao.retention_hold_dao import RetentionHoldDao
from src.database.dao.retention_audit_event_dao import RetentionAuditEventDao
from src.database.dao.retention_run_dao import RetentionRunDao
from src.database.repositories.mappers.retention_db_vs_entity_mapper import (
    RetentionDBVSEntityMapper,
)
from src.database.repositories.retention_repository import RetentionRepository
from src.retention.models import DataCategory, RetentionAuditEvent, RetentionRun


class PostgresRetentionRepository(RetentionRepository):
    def save(self, entity: RetentionRun) -> None:
        self.save_run(entity)

    def get(self, entity_id: str) -> Optional[RetentionRun]:
        return self.get_run(entity_id)

    def get_all(self) -> List[RetentionRun]:
        return self.list_runs()

    def update(self, entity_id: str, entity: RetentionRun) -> None:
        self.update_run(entity)

    def upsert(self, entity: RetentionRun) -> None:
        self.save_run(entity)

    def save_run(self, run: RetentionRun) -> None:
        self.database_session.add(RetentionDBVSEntityMapper.map_run_to_db(run))
        self.database_session.flush()

    def update_run(self, run: RetentionRun) -> None:
        row = (
            self.database_session.query(RetentionRunDao)
            .filter(RetentionRunDao.id == run.run_id)
            .first()
        )
        if not row:
            self.save_run(run)
            return
        RetentionDBVSEntityMapper.update_run_dao(row, run)
        self.database_session.flush()

    def get_run(self, run_id: str) -> Optional[RetentionRun]:
        row = (
            self.database_session.query(RetentionRunDao)
            .filter(RetentionRunDao.id == run_id)
            .first()
        )
        return RetentionDBVSEntityMapper.map_run_to_entity(row) if row else None

    def list_runs(self, limit: int = 20) -> List[RetentionRun]:
        rows = (
            self.database_session.query(RetentionRunDao)
            .order_by(RetentionRunDao.started_at.desc())
            .limit(limit)
            .all()
        )
        return [RetentionDBVSEntityMapper.map_run_to_entity(row) for row in rows]

    def add_audit_event(self, event: RetentionAuditEvent) -> None:
        self.database_session.add(RetentionDBVSEntityMapper.map_audit_to_db(event))
        self.database_session.flush()

    def list_audit_events(self, limit: int = 100) -> List[RetentionAuditEvent]:
        rows = (
            self.database_session.query(RetentionAuditEventDao)
            .order_by(RetentionAuditEventDao.created_at.desc())
            .limit(limit)
            .all()
        )
        return [RetentionDBVSEntityMapper.map_audit_to_entity(row) for row in rows]

    def is_category_held(self, category: DataCategory) -> bool:
        return (
            self.database_session.query(RetentionHoldDao)
            .filter(
                RetentionHoldDao.data_category == category.value,
                RetentionHoldDao.active.is_(True),
            )
            .first()
            is not None
        )

    def add_hold(self, category: DataCategory, reason: str, entity_id: Optional[str] = None) -> str:
        hold_id = str(uuid4())
        self.database_session.add(
            RetentionHoldDao(
                id=hold_id,
                data_category=category.value,
                entity_id=entity_id,
                reason=reason,
                active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.database_session.flush()
        return hold_id

    def release_hold(self, hold_id: str) -> bool:
        row = (
            self.database_session.query(RetentionHoldDao)
            .filter(RetentionHoldDao.id == hold_id)
            .first()
        )
        if not row:
            return False
        row.active = False
        row.released_at = datetime.now(timezone.utc)
        self.database_session.flush()
        return True
