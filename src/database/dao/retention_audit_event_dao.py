from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class RetentionAuditEventDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "retention_audit_events"

    id = Column(String(36), primary_key=True)
    event_type = Column(String(32), nullable=False, index=True)
    policy_id = Column(String(64), nullable=True, index=True)
    actor = Column(String(64), nullable=True)
    old_value = Column(JSON_TYPE, nullable=True)
    new_value = Column(JSON_TYPE, nullable=True)
    run_id = Column(String(36), nullable=True, index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)  # pylint: disable=not-callable
