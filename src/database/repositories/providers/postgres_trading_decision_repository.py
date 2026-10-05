from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.database.dao.trading_decision_dao import TradingDecisionDao
from src.database.repositories.mappers.trading_decision_db_vs_entity_mapper import (
    TradingDecisionDbVsEntityMapper,
)
from src.database.repositories.trading_decision_repository import (
    TradingDecisionRepository,
)
from src.trading.decision.trading_decision import TradingDecision


class PostgresTradingDecisionRepository(TradingDecisionRepository):
    def save(self, entity: TradingDecision) -> TradingDecision:
        dao = TradingDecisionDbVsEntityMapper.map_to_db(entity)
        merged_dao = self.database_session.merge(dao)
        self.database_session.flush()
        return TradingDecisionDbVsEntityMapper.map_to_entity(merged_dao)

    def get(self, entity_id: str) -> Optional[TradingDecision]:
        dao = (
            self.database_session.query(TradingDecisionDao)
            .filter(TradingDecisionDao.id == entity_id)
            .first()
        )
        if not dao:
            return None
        return TradingDecisionDbVsEntityMapper.map_to_entity(dao)

    def get_all(self) -> List[TradingDecision]:
        return self.list_decisions(limit=1000)

    def update(self, entity_id: str, entity: TradingDecision):
        return self.save(entity)

    def upsert(self, entity: TradingDecision) -> None:
        self.save(entity)

    def get_by_order_id(self, order_id: str) -> Optional[TradingDecision]:
        dao = (
            self.database_session.query(TradingDecisionDao)
            .filter(TradingDecisionDao.resulting_order_id == order_id)
            .first()
        )
        if not dao:
            return None
        return TradingDecisionDbVsEntityMapper.map_to_entity(dao)

    def get_by_ticker_symbol(
            self, ticker_symbol: str, limit: int = 50
    ) -> List[TradingDecision]:
        daos = (
            self.database_session.query(TradingDecisionDao)
            .filter(TradingDecisionDao.ticker_symbol == ticker_symbol)
            .order_by(TradingDecisionDao.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [TradingDecisionDbVsEntityMapper.map_to_entity(d) for d in daos]

    def get_by_commit_hash(self, commit_hash: str) -> List[TradingDecision]:
        daos = (
            self.database_session.query(TradingDecisionDao)
            .filter(TradingDecisionDao.commit_hash == commit_hash)
            .order_by(TradingDecisionDao.timestamp.desc())
            .all()
        )
        return [TradingDecisionDbVsEntityMapper.map_to_entity(d) for d in daos]

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def list_decisions(
            self,
            ticker_symbol: Optional[str] = None,
            exchange: Optional[str] = None,
            status: Optional[str] = None,
            since: Optional[datetime] = None,
            until: Optional[datetime] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[TradingDecision]:
        query = self.database_session.query(TradingDecisionDao)
        if ticker_symbol:
            query = query.filter(TradingDecisionDao.ticker_symbol == ticker_symbol)
        if exchange:
            query = query.filter(TradingDecisionDao.exchange == exchange)
        if status:
            query = query.filter(TradingDecisionDao.status == status)
        if since:
            query = query.filter(TradingDecisionDao.timestamp >= since)
        if until:
            query = query.filter(TradingDecisionDao.timestamp <= until)

        query = query.order_by(TradingDecisionDao.timestamp.desc())
        query = query.offset(offset).limit(limit)
        return [TradingDecisionDbVsEntityMapper.map_to_entity(d) for d in query.all()]
