from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, cast

from sqlalchemy import and_, or_

from src.database.dao.walk_forward_dao import WalkForwardRunDao
from src.database.repositories.walk_forward_repository import WalkForwardRepository


class PostgresWalkForwardRepository(WalkForwardRepository):

    def save(self, entity: WalkForwardRunDao) -> WalkForwardRunDao:
        self.save_run(
            run_id=entity.id,
            ticker_symbol=entity.ticker_symbol,
            status=entity.status,
            spec=entity.spec or {},
            summary=entity.summary,
        )
        return entity

    def get(self, entity_id: str) -> Optional[WalkForwardRunDao]:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == entity_id)
            .first()
        )
        return cast(Optional[WalkForwardRunDao], row)

    def get_all(self) -> List[WalkForwardRunDao]:
        rows = (
            self.database_session.query(WalkForwardRunDao)
            .order_by(WalkForwardRunDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[WalkForwardRunDao], rows)

    def update(self, entity_id: str, entity: WalkForwardRunDao) -> None:
        self.save(entity)

    def upsert(self, entity: WalkForwardRunDao) -> None:
        self.save(entity)

    def save_run(
            self,
            run_id: str,
            ticker_symbol: str,
            status: str,
            spec: dict[str, Any],
            summary: Optional[dict[str, Any]] = None,
            worker_id: Optional[str] = None,
            started_at: Optional[datetime] = None,
            completed_at: Optional[datetime] = None,
            heartbeat_at: Optional[datetime] = None,
            lease_expires_at: Optional[datetime] = None,
            error_message: Optional[str] = None,
    ) -> None:
        existing = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if existing:
            existing.status = status
            existing.spec = spec
            if summary is not None:
                existing.summary = summary
            if worker_id is not None:
                existing.worker_id = worker_id
            if started_at is not None:
                existing.started_at = started_at
            if completed_at is not None:
                existing.completed_at = completed_at
            if heartbeat_at is not None:
                existing.heartbeat_at = heartbeat_at
            if lease_expires_at is not None:
                existing.lease_expires_at = lease_expires_at
            if error_message is not None:
                existing.error_message = error_message
        else:
            self.database_session.add(
                WalkForwardRunDao(
                    id=run_id,
                    ticker_symbol=ticker_symbol,
                    status=status,
                    spec=spec,
                    summary=summary,
                    worker_id=worker_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    heartbeat_at=heartbeat_at,
                    lease_expires_at=lease_expires_at,
                    error_message=error_message,
                )
            )
        self.database_session.flush()

    def update_run_summary(
            self,
            run_id: str,
            status: str,
            summary: dict[str, Any],
    ) -> None:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if row:
            row.status = status
            row.summary = summary
            self.database_session.flush()

    @staticmethod
    def _extract_classification(verdict: str) -> str:
        if "ROBUST" in verdict:
            return "ROBUST"
        if "UNSTABLE" in verdict:
            return "UNSTABLE"
        return "DETERIORATING"

    @staticmethod
    def _normalize_folds(raw_folds: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_folds, list):
            return []
        folds_list: list[dict[str, Any]] = []
        for f in raw_folds:
            if isinstance(f, dict):
                f_copy = dict(f)
                f_copy.setdefault("out_of_sample_trades", f_copy.get("test_trades_count", 0))
                f_copy.setdefault("in_sample_trades", 0)
                folds_list.append(f_copy)
            else:
                folds_list.append(f)
        return folds_list

    @classmethod
    def _normalize_summary(cls, summary: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(summary, dict):
            return summary
        norm = dict(summary)
        norm.setdefault("out_of_sample_return_pct", norm.get("aggregate_oos_return_pct"))
        norm.setdefault("max_out_of_sample_drawdown_pct", norm.get("max_oos_drawdown_pct"))
        norm.setdefault("walk_forward_efficiency_ratio", norm.get("walk_forward_efficiency"))
        if "stability_classification" not in norm and "verdict" in norm:
            norm["stability_classification"] = cls._extract_classification(str(norm["verdict"]))
        if "folds" not in norm and "fold_results" in norm:
            norm["folds"] = cls._normalize_folds(norm["fold_results"])
        return norm

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if not row:
            return None
        norm_summary = self._normalize_summary(row.summary)
        error_msg = (
            norm_summary.get("error_message") or norm_summary.get("error")
            if isinstance(norm_summary, dict)
            else None
        )
        spec = row.spec if isinstance(row.spec, dict) else {}
        config = spec.get("configuration", {}) if isinstance(spec.get("configuration"), dict) else {}
        ds = spec.get("data_source", {}) if isinstance(spec.get("data_source"), dict) else {}
        vcs_commit_hash = (
            (norm_summary.get("vcs_commit_hash") if isinstance(norm_summary, dict) else None)
            or config.get("vcs_commit_hash")
        )
        software_version = (
            (norm_summary.get("software_version") if isinstance(norm_summary, dict) else None)
            or spec.get("software_version")
        )
        dataset_identity = (
            (norm_summary.get("dataset_identity") if isinstance(norm_summary, dict) else None)
            or ds.get("dataset_id")
            or ds.get("path")
            or ds.get("source_type")
        )
        return {
            "id": row.id,
            "run_id": row.id,
            "ticker_symbol": row.ticker_symbol,
            "status": row.status,
            "spec": row.spec,
            "summary": norm_summary,
            "performance_summary": norm_summary,
            "vcs_commit_hash": vcs_commit_hash,
            "software_version": software_version,
            "dataset_identity": dataset_identity,
            "error_message": row.error_message or error_msg,
            "worker_id": row.worker_id,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
            "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self.database_session.query(WalkForwardRunDao)
            .order_by(WalkForwardRunDao.created_at.desc())
            .limit(limit)
            .all()
        )
        typed_rows = cast(List[WalkForwardRunDao], rows)
        result: list[dict[str, Any]] = []
        for r in typed_rows:
            norm = self._normalize_summary(r.summary)
            err = (
                r.error_message
                or (
                    norm.get("error_message") or norm.get("error")
                    if isinstance(norm, dict)
                    else None
                )
            )
            spec = r.spec if isinstance(r.spec, dict) else {}
            config = spec.get("configuration", {}) if isinstance(spec.get("configuration"), dict) else {}
            ds = spec.get("data_source", {}) if isinstance(spec.get("data_source"), dict) else {}
            vcs_commit_hash = (
                (norm.get("vcs_commit_hash") if isinstance(norm, dict) else None)
                or config.get("vcs_commit_hash")
            )
            software_version = (
                (norm.get("software_version") if isinstance(norm, dict) else None)
                or spec.get("software_version")
            )
            dataset_identity = (
                (norm.get("dataset_identity") if isinstance(norm, dict) else None)
                or ds.get("dataset_id")
                or ds.get("path")
                or ds.get("source_type")
            )
            result.append(
                {
                    "id": r.id,
                    "run_id": r.id,
                    "ticker_symbol": r.ticker_symbol,
                    "status": r.status,
                    "spec": r.spec,
                    "summary": norm,
                    "performance_summary": norm,
                    "vcs_commit_hash": vcs_commit_hash,
                    "software_version": software_version,
                    "dataset_identity": dataset_identity,
                    "error_message": err,
                    "worker_id": r.worker_id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "heartbeat_at": r.heartbeat_at.isoformat() if r.heartbeat_at else None,
                    "lease_expires_at": r.lease_expires_at.isoformat() if r.lease_expires_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            )
        return result

    def acquire_next_queued_run(self, worker_id: str, lease_duration_seconds: int) -> Optional[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        lease_expires = now + timedelta(seconds=lease_duration_seconds)
        query = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.status == "QUEUED")
            .order_by(WalkForwardRunDao.created_at.asc())
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
        return self.get_run(row.id)

    def acquire_run(self, run_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id, WalkForwardRunDao.status == "QUEUED")
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

    def renew_lease(self, run_id: str, worker_id: str, lease_duration_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
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

    def mark_completed(self, run_id: str, summary: dict[str, Any]) -> None:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if row:
            row.status = "COMPLETED"
            row.summary = summary
            row.completed_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            self.database_session.flush()

    def mark_failed(self, run_id: str, error_message: str, summary: Optional[dict[str, Any]] = None) -> None:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if row:
            row.status = "FAILED"
            row.error_message = error_message
            if summary:
                row.summary = summary
            row.completed_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            self.database_session.flush()

    def mark_cancelled(self, run_id: str, reason: Optional[str] = None) -> bool:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
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

    def recover_abandoned_runs(self, timeout_seconds: int) -> list[str]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        abandoned_rows = (
            self.database_session.query(WalkForwardRunDao)
            .filter(
                WalkForwardRunDao.status == "RUNNING",
                or_(
                    WalkForwardRunDao.lease_expires_at < now,
                    and_(
                        WalkForwardRunDao.lease_expires_at.is_(None),
                        or_(
                            WalkForwardRunDao.heartbeat_at < cutoff,
                            and_(WalkForwardRunDao.heartbeat_at.is_(None), WalkForwardRunDao.created_at < cutoff),
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

    def count_active_runs(self) -> int:
        return (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.status == "RUNNING")
            .count()
        )

    def is_run_active(self, run_id: str) -> bool:
        row = (
            self.database_session.query(WalkForwardRunDao.status)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        return bool(row and row[0] in ("QUEUED", "RUNNING"))
