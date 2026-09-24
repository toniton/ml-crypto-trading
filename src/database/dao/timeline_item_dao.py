from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class TimelineItemDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "timeline_items"

    id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="INFO", index=True)
    title = Column(String(256), nullable=False)
    summary = Column(Text, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    causation_id = Column(String(64), nullable=True)
    actor_type = Column(String(32), nullable=True, index=True)
    actor_id = Column(String(64), nullable=True)
    primary_entity_type = Column(String(32), nullable=True, index=True)
    primary_entity_id = Column(String(64), nullable=True, index=True)
    entities = Column(JSON_TYPE, nullable=True)
    artifacts = Column(JSON_TYPE, nullable=True)
    metadata_ = Column("metadata", JSON_TYPE, server_default="{}", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
