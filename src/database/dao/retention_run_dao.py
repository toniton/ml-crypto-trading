from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class RetentionRunDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "retention_runs"

    id = Column(String(36), primary_key=True)
    status = Column(String(16), nullable=False, index=True)
    trigger = Column(String(16), nullable=False)
    dry_run = Column(Boolean, nullable=False, default=True)
    policy_version = Column(String(32), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    categories = Column(JSON_TYPE, nullable=False, default=list)
    storage_reclaimed_bytes = Column(BigInteger, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
