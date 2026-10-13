from __future__ import annotations

from typing import Any, List, Optional, cast

from src.database.dao.experiment_dao import ExperimentDao
from src.database.repositories.experiment_repository import ExperimentRepository


class PostgresExperimentRepository(ExperimentRepository):

    def save(self, entity: ExperimentDao) -> ExperimentDao:
        self.save_experiment(
            experiment_id=entity.id,
            name=entity.name,
            ticker_symbol=entity.ticker_symbol,
            branch_id=entity.branch_id,
            base_commit_hash=entity.base_commit_hash,
            status=entity.status,
            spec=entity.spec or {},
            run_bindings=entity.run_bindings or [],
            report=entity.report,
        )
        return entity

    def get(self, entity_id: str) -> Optional[ExperimentDao]:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == entity_id)
            .first()
        )
        return cast(Optional[ExperimentDao], row)

    def get_all(self) -> List[ExperimentDao]:
        rows = (
            self.database_session.query(ExperimentDao)
            .order_by(ExperimentDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[ExperimentDao], rows)

    def update(self, entity_id: str, entity: ExperimentDao) -> None:
        self.save(entity)

    def upsert(self, entity: ExperimentDao) -> None:
        self.save(entity)

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
        existing = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if existing:
            existing.name = name
            existing.ticker_symbol = ticker_symbol
            existing.branch_id = branch_id
            existing.base_commit_hash = base_commit_hash
            existing.status = status
            existing.spec = spec
            existing.run_bindings = run_bindings
            existing.report = report
        else:
            self.database_session.add(
                ExperimentDao(
                    id=experiment_id,
                    name=name,
                    ticker_symbol=ticker_symbol,
                    branch_id=branch_id,
                    base_commit_hash=base_commit_hash,
                    status=status,
                    spec=spec,
                    run_bindings=run_bindings,
                    report=report,
                )
            )
        self.database_session.flush()

    def update_status(
            self,
            experiment_id: str,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if row:
            row.status = status
            if error_message:
                current_report = dict(row.report or {})
                current_report["error_message"] = error_message
                row.report = current_report
            self.database_session.flush()

    def update_bindings(
            self,
            experiment_id: str,
            run_bindings: list[dict[str, Any]],
    ) -> None:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if row:
            row.run_bindings = run_bindings
            self.database_session.flush()

    def update_report(
            self,
            experiment_id: str,
            status: str,
            report: dict[str, Any],
    ) -> None:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if row:
            row.status = status
            row.report = report
            self.database_session.flush()

    def delete_experiment(self, experiment_id: str) -> bool:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if not row:
            return False
        self.database_session.delete(row)
        self.database_session.flush()
        return True

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        row = (
            self.database_session.query(ExperimentDao)
            .filter(ExperimentDao.id == experiment_id)
            .first()
        )
        if not row:
            return None
        return self._to_dict(row)

    def list_experiments(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = (
            self.database_session.query(ExperimentDao)
            .order_by(ExperimentDao.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: ExperimentDao) -> dict[str, Any]:
        return {
            "experiment_id": row.id,
            "id": row.id,
            "name": row.name,
            "ticker_symbol": row.ticker_symbol,
            "branch_id": row.branch_id,
            "base_commit_hash": row.base_commit_hash,
            "status": row.status,
            "spec": row.spec or {},
            "candidates": (row.spec or {}).get("candidates", []),
            "run_bindings": row.run_bindings or [],
            "report": row.report,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
