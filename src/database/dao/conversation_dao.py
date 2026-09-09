from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class ConversationDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # pylint: disable=not-callable
