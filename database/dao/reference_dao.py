from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, func

from database.database_manager import DatabaseManager


class ReferenceDao(DatabaseManager.BaseTableModel):
    __tablename__ = "vcs_refs"

    name = Column(String(255), primary_key=True)
    commit_hash = Column(String(64), ForeignKey("vcs_commits.hash", ondelete="RESTRICT"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # pylint: disable=not-callable
