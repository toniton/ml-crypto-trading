from __future__ import annotations

from typing import Any, List, Optional, cast

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
    ) -> None:
        existing = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if existing:
            existing.status = status
            existing.spec = spec
            existing.summary = summary
        else:
            self.database_session.add(
                WalkForwardRunDao(
                    id=run_id,
                    ticker_symbol=ticker_symbol,
                    status=status,
                    spec=spec,
                    summary=summary,
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

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(WalkForwardRunDao)
            .filter(WalkForwardRunDao.id == run_id)
            .first()
        )
        if not row:
            return None
        return {
            "id": row.id,
            "ticker_symbol": row.ticker_symbol,
            "status": row.status,
            "spec": row.spec,
            "summary": row.summary,
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
        return [
            {
                "id": r.id,
                "ticker_symbol": r.ticker_symbol,
                "status": r.status,
                "spec": r.spec,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in typed_rows
        ]
