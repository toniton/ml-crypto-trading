from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, String, Text, func

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class RetentionHoldDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "retention_holds"

    id = Column(String(36), primary_key=True)
    data_category = Column(String(32), nullable=False, index=True)
    entity_id = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
    released_at = Column(DateTime(timezone=True), nullable=True)
