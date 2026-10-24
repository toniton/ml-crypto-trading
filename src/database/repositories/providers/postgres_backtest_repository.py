from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert

from src.backtest.domain.metrics import BacktestMetrics
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.database.dao.backtest_result_dao import BacktestResultDao
from src.database.dao.backtest_session_dao import BacktestSessionDao
from src.database.repositories.backtest_repository import BacktestRepository
from src.database.repositories.mappers.backtest_db_vs_entity_mapper import BacktestDBVSEntityMapper


class PostgresBacktestRepository(BacktestRepository):

    def save(self, entity: BacktestSession) -> BacktestSession:
        self.save_session(entity)
        return entity

    def get(self, entity_id: str) -> Optional[BacktestSession]:
        return self.get_session(entity_id)

    def get_all(self) -> List[BacktestSession]:
        return self.list_sessions(limit=100)

    def update(self, entity_id: str, entity: BacktestSession) -> None:
        self.update_session(entity)

    def upsert(self, entity: BacktestSession) -> None:
        self.save_session(entity)

    def save_session(self, session: BacktestSession) -> None:
        dao = BacktestDBVSEntityMapper.session_to_dao(session)
        stmt = insert(BacktestSessionDao).values(
            id=dao.id,
            ticker_symbol=dao.ticker_symbol,
            status=dao.status,
            config=dao.config,
            worker_id=dao.worker_id,
            started_at=dao.started_at,
            completed_at=dao.completed_at,
            heartbeat_at=dao.heartbeat_at,
            lease_expires_at=dao.lease_expires_at,
            error_message=dao.error_message,
            created_at=dao.created_at,
            updated_at=dao.updated_at,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": dao.status,
                "config": dao.config,
                "worker_id": dao.worker_id,
                "started_at": dao.started_at,
                "completed_at": dao.completed_at,
                "heartbeat_at": dao.heartbeat_at,
                "lease_expires_at": dao.lease_expires_at,
                "error_message": dao.error_message,
                "updated_at": dao.updated_at,
            },
        )
        self.database_session.execute(stmt)

    def update_session(self, session: BacktestSession) -> None:
        self.save_session(session)

    def get_session(self, session_id: str) -> Optional[BacktestSession]:
        dao = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        return BacktestDBVSEntityMapper.dao_to_session(dao) if dao else None

    def list_sessions(self, limit: int = 50) -> list[BacktestSession]:
        rows = (
            self.database_session.query(BacktestSessionDao)
            .order_by(BacktestSessionDao.created_at.desc())
            .limit(limit)
            .all()
        )
        return [BacktestDBVSEntityMapper.dao_to_session(row) for row in rows]

    def save_result(
            self,
            result: BacktestResult,
            metrics: Optional[BacktestMetrics | dict[str, Any]] = None,
    ) -> None:
        dao = BacktestDBVSEntityMapper.result_to_dao(result, metrics)
        stmt = insert(BacktestResultDao).values(
            session_id=dao.session_id,
            ticker_symbol=dao.ticker_symbol,
            data=dao.data,
        ).on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "data": dao.data,
            },
        )
        self.database_session.execute(stmt)

    def get_result(self, session_id: str) -> Optional[BacktestResult]:
        dao = (
            self.database_session.query(BacktestResultDao)
            .filter(BacktestResultDao.session_id == session_id)
            .first()
        )
        return BacktestDBVSEntityMapper.dao_to_result(dao) if dao else None

    def get_result_metrics(self, session_id: str) -> Optional[dict[str, Any]]:
        dao = (
            self.database_session.query(BacktestResultDao)
            .filter(BacktestResultDao.session_id == session_id)
            .first()
        )
        if dao and dao.data and isinstance(dao.data, dict):
            return dao.data.get("metrics")
        return None

    def acquire_next_queued_session(self, worker_id: str, lease_duration_seconds: int) -> Optional[BacktestSession]:
        now = datetime.now(timezone.utc)
        lease_expires = now + timedelta(seconds=lease_duration_seconds)
        query = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.status == "QUEUED")
            .order_by(BacktestSessionDao.created_at.asc())
        )
        try:
            row = query.with_for_update(skip_locked=True).first()
        except Exception:
            row = query.first()

        if not row:
            return None

        row.status = "RUNNING"
        row.worker_id = worker_id
        row.started_at = now
        row.heartbeat_at = now
        row.lease_expires_at = lease_expires
        self.database_session.flush()
        return BacktestDBVSEntityMapper.dao_to_session(row)

    def acquire_session(self, session_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        row = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id, BacktestSessionDao.status == "QUEUED")
            .first()
        )
        if not row:
            return False
        row.status = "RUNNING"
        row.worker_id = worker_id
        row.started_at = now
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
        self.database_session.flush()
        return True

    def renew_lease(self, session_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        row = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        if row and row.status == "RUNNING":
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            if worker_id:
                row.worker_id = worker_id
            self.database_session.flush()
            return True
        return False

    def mark_completed(
            self,
            session_id: str,
            result: BacktestResult,
            metrics: Optional[BacktestMetrics | dict[str, Any]] = None,
    ) -> None:
        row = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        if row:
            row.status = "COMPLETED"
            row.completed_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            self.database_session.flush()
        self.save_result(result, metrics=metrics)

    def mark_failed(self, session_id: str, error_message: str) -> None:
        row = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        if row:
            row.status = "FAILED"
            row.error_message = error_message
            row.completed_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            self.database_session.flush()

    def mark_cancelled(self, session_id: str, reason: Optional[str] = None) -> bool:
        row = (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        if row and row.status in ("QUEUED", "RUNNING"):
            row.status = "CANCELLED"
            row.error_message = reason or "Run cancelled by user"
            row.completed_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            self.database_session.flush()
            return True
        return False

    def recover_abandoned_sessions(self, timeout_seconds: int) -> list[str]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        abandoned_rows = (
            self.database_session.query(BacktestSessionDao)
            .filter(
                BacktestSessionDao.status == "RUNNING",
                or_(
                    BacktestSessionDao.lease_expires_at < now,
                    and_(
                        BacktestSessionDao.lease_expires_at.is_(None),
                        or_(
                            BacktestSessionDao.heartbeat_at < cutoff,
                            and_(BacktestSessionDao.heartbeat_at.is_(None), BacktestSessionDao.created_at < cutoff),
                        ),
                    ),
                ),
            )
            .all()
        )
        recovered_ids: list[str] = []
        for r in abandoned_rows:
            r.status = "FAILED"
            r.error_message = "Abandoned: worker lease expired or process shutdown"
            r.completed_at = now
            r.lease_expires_at = None
            recovered_ids.append(r.id)
        if recovered_ids:
            self.database_session.flush()
        return recovered_ids

    def count_active_sessions(self) -> int:
        return (
            self.database_session.query(BacktestSessionDao)
            .filter(BacktestSessionDao.status == "RUNNING")
            .count()
        )

    def is_session_active(self, session_id: str) -> bool:
        row = (
            self.database_session.query(BacktestSessionDao.status)
            .filter(BacktestSessionDao.id == session_id)
            .first()
        )
        return bool(row and row[0] in ("QUEUED", "RUNNING"))
