from __future__ import annotations

from typing import Any, List, Optional

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
            created_at=dao.created_at,
            updated_at=dao.updated_at,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": dao.status,
                "config": dao.config,
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
