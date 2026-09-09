from __future__ import annotations

from sqlalchemy import Column, DateTime, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class BlobDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "vcs_blobs"

    hash = Column(String(64), primary_key=True)
    content = Column(JSON_TYPE, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
