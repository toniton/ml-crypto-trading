from __future__ import annotations

from sqlalchemy import Column, DateTime, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB

from src.database.database_manager import DatabaseManager

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class BlobDao(DatabaseManager.BaseTableModel):
    __tablename__ = "vcs_blobs"

    hash = Column(String(64), primary_key=True)
    content = Column(JSON_TYPE, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
