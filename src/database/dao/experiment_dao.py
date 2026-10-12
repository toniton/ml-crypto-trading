from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class ExperimentDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "experiments"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    ticker_symbol = Column(String(32), nullable=False, index=True)
    branch_id = Column(String(64), nullable=False, index=True)
    base_commit_hash = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    spec = Column(JSON_TYPE, nullable=False)
    run_bindings = Column(JSON_TYPE, nullable=False, default=list)
    report = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)  # pylint: disable=not-callable
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # pylint: disable=not-callable
