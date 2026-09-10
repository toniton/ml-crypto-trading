from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class BacktestSessionDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "backtest_sessions"

    id = Column(String(64), primary_key=True)
    ticker_symbol = Column(String(32), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="RUNNING")
    config = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)  # pylint: disable=not-callable
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # pylint: disable=not-callable

