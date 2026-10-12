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
        return {
            "id": row.id,
            "run_id": row.id,
            "ticker_symbol": row.ticker_symbol,
            "status": row.status,
            "spec": row.spec,
            "summary": norm_summary,
            "performance_summary": norm_summary,
            "error_message": error_msg,
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
                norm.get("error_message") or norm.get("error")
                if isinstance(norm, dict)
                else None
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
                    "error_message": err,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            )
        return result
