from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class PromotionRecordDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "promotion_records"

    id = Column(String(64), primary_key=True)
    idempotency_key = Column(String(64), nullable=False, unique=True, index=True)
    experiment_id = Column(String(64), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=False)
    source_commit = Column(String(64), nullable=False)
    target_ref = Column(String(64), nullable=False)
    merge_commit_hash = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="PROMOTED", index=True)
    approver = Column(String(64), nullable=False)
    approval_notes = Column(Text, nullable=True)
    gate_results = Column(JSON_TYPE, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        onupdate=func.now(),  # pylint: disable=not-callable
        nullable=False,
    )
