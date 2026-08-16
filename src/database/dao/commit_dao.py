from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.database_manager import DatabaseManager


class CommitDao(DatabaseManager.BaseTableModel):
    __tablename__ = "vcs_commits"

    hash = Column(String(64), primary_key=True)
    blob_hash = Column(String(64), ForeignKey("vcs_blobs.hash", ondelete="RESTRICT"), nullable=False)
    parent_hash = Column(String(64), ForeignKey("vcs_commits.hash", ondelete="RESTRICT"), nullable=True)
    author = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON_TYPE, server_default="{}", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
