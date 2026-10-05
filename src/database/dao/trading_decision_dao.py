from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class TradingDecisionDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "trading_decisions"

    id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ticker_symbol = Column(String(32), nullable=False, index=True)
    exchange = Column(String(32), nullable=False, index=True)
    trade_action = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    commit_hash = Column(String(64), nullable=True, index=True)
    winning_strategy = Column(String(64), nullable=True)
    resulting_order_id = Column(String(64), nullable=True, index=True)
    market_snapshot = Column(JSON_TYPE, nullable=False, server_default="{}")
    regime_snapshot = Column(JSON_TYPE, nullable=False, server_default="{}")
    consensus_snapshot = Column(JSON_TYPE, nullable=False, server_default="{}")
    sizing_snapshot = Column(JSON_TYPE, nullable=False, server_default="{}")
    portfolio_snapshot = Column(JSON_TYPE, nullable=False, server_default="{}")
    risk_evaluation = Column(JSON_TYPE, nullable=False, server_default="{}")
    health_evaluation = Column(JSON_TYPE, nullable=True)
    metadata_ = Column("metadata", JSON_TYPE, server_default="{}", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
