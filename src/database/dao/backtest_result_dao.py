from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class BacktestResultDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(64),
        ForeignKey("backtest_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    ticker_symbol = Column(String(32), nullable=False, index=True)
    data = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable

