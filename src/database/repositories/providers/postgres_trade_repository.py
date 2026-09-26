from __future__ import annotations

from datetime import datetime
from typing import Optional, cast

from sqlalchemy.dialects.postgresql import insert

from api.interfaces.trade import Trade
from src.database.dao.trade_dao import TradeDao
from src.database.repositories.mappers.trade_db_vs_entity_mapper import TradeDBVSEntityMapper
from src.database.repositories.trade_repository import TradeRepository


class PostgresTradeRepository(TradeRepository):

    def save(self, entity: Trade) -> None:
        trade_dao = TradeDBVSEntityMapper.map_to_db(entity)
        self.database_session.add(trade_dao)

    def get(self, entity_id: str) -> Optional[Trade]:
        row = (
            self.database_session.query(TradeDao)
            .filter(TradeDao.trade_id == entity_id)
            .first()
        )
        return TradeDBVSEntityMapper.map_to_entity(cast(TradeDao, row)) if row else None

    def get_all(self) -> list[Trade]:
        query = self.database_session.query(TradeDao).order_by(TradeDao.exit_timestamp.asc())
        return [
            TradeDBVSEntityMapper.map_to_entity(cast(TradeDao, row))
            for row in query.all()
        ]

    def update(self, entity_id: str, entity: Trade) -> None:
        trade_dao = TradeDBVSEntityMapper.map_to_db(entity)
        self.database_session.query(TradeDao).filter(
            TradeDao.trade_id == entity_id
        ).update({
            TradeDao.exit_price: trade_dao.exit_price,
            TradeDao.gross_pnl: trade_dao.gross_pnl,
            TradeDao.fees: trade_dao.fees,
            TradeDao.slippage: trade_dao.slippage,
            TradeDao.net_pnl: trade_dao.net_pnl,
            TradeDao.return_pct: trade_dao.return_pct,
            TradeDao.duration_seconds: trade_dao.duration_seconds,
            TradeDao.exit_timestamp: trade_dao.exit_timestamp,
            TradeDao.metadata_: trade_dao.metadata_,
        })

    def upsert(self, entity: Trade) -> None:
        trade_dao = TradeDBVSEntityMapper.map_to_db(entity)
        insert_statement = insert(TradeDao).values(
            trade_id=trade_dao.trade_id,
            ticker_symbol=trade_dao.ticker_symbol,
            entry_order_uuid=trade_dao.entry_order_uuid,
            exit_order_uuid=trade_dao.exit_order_uuid,
            entry_price=trade_dao.entry_price,
            exit_price=trade_dao.exit_price,
            quantity=trade_dao.quantity,
            gross_pnl=trade_dao.gross_pnl,
            fees=trade_dao.fees,
            slippage=trade_dao.slippage,
            net_pnl=trade_dao.net_pnl,
            return_pct=trade_dao.return_pct,
            duration_seconds=trade_dao.duration_seconds,
            entry_timestamp=trade_dao.entry_timestamp,
            exit_timestamp=trade_dao.exit_timestamp,
            metadata_=trade_dao.metadata_,
        )
        set_values = {
            TradeDao.exit_price: trade_dao.exit_price,
            TradeDao.gross_pnl: trade_dao.gross_pnl,
            TradeDao.fees: trade_dao.fees,
            TradeDao.slippage: trade_dao.slippage,
            TradeDao.net_pnl: trade_dao.net_pnl,
            TradeDao.return_pct: trade_dao.return_pct,
            TradeDao.duration_seconds: trade_dao.duration_seconds,
            TradeDao.exit_timestamp: trade_dao.exit_timestamp,
        }
        if trade_dao.metadata_ is not None:
            set_values[TradeDao.metadata_] = trade_dao.metadata_

        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["trade_id"],
            set_=set_values,
        )
        self.database_session.execute(upsert_statement)

    def get_by_ticker_symbol(self, ticker_symbol: str) -> list[Trade]:
        symbols = {
            ticker_symbol,
            ticker_symbol.replace("_", "/"),
            ticker_symbol.replace("/", "_"),
            ticker_symbol.replace("-", "_"),
            ticker_symbol.replace("_", "-"),
        }
        query = self.database_session.query(TradeDao).filter(
            TradeDao.ticker_symbol.in_(list(symbols))
        ).order_by(TradeDao.exit_timestamp.asc())
        return [
            TradeDBVSEntityMapper.map_to_entity(cast(TradeDao, row))
            for row in query.all()
        ]

    def get_by_exit_range(
            self, ticker_symbol: Optional[str], start: datetime, end: datetime
    ) -> list[Trade]:
        query = self.database_session.query(TradeDao).filter(
            TradeDao.exit_timestamp >= start,
            TradeDao.exit_timestamp < end,
        )
        if ticker_symbol:
            symbols = {
                ticker_symbol,
                ticker_symbol.replace("_", "/"),
                ticker_symbol.replace("/", "_"),
                ticker_symbol.replace("-", "_"),
                ticker_symbol.replace("_", "-"),
            }
            query = query.filter(TradeDao.ticker_symbol.in_(list(symbols)))

        query = query.order_by(TradeDao.exit_timestamp.asc())
        return [
            TradeDBVSEntityMapper.map_to_entity(cast(TradeDao, row))
            for row in query.all()
        ]
