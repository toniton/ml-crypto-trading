from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class ScorecardSnapshotDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "scorecard_snapshots"

    snapshot_id = Column(String(64), primary_key=True)
    symbol = Column(String(32), nullable=False, index=True)
    branch = Column(String(128), nullable=False, default="main")
    commit_hash = Column(String(64), nullable=True, index=True)
    trigger = Column(String(32), nullable=False, default="manual", index=True)
    current_stage = Column(String(32), nullable=False, default="DRAFT")
    drifted = Column(Boolean, nullable=True)
    live_return_pct = Column(Float, nullable=True)
    oos_return_pct = Column(Float, nullable=True)
    backtest_return_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    payload = Column(JSON_TYPE, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
        index=True,
    )
