from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class PromotionAuditEventDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "promotion_audit_events"

    id = Column(String(64), primary_key=True)
    promotion_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    from_state = Column(String(32), nullable=True)
    to_state = Column(String(32), nullable=False, index=True)
    actor = Column(String(64), nullable=False)
    payload = Column(JSON_TYPE, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
        index=True,
    )
