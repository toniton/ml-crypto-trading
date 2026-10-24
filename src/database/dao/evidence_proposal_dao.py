from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class EvidenceProposalDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "evidence_proposals"

    id = Column(String(64), primary_key=True)
    experiment_id = Column(String(64), nullable=True, index=True)
    ticker_symbol = Column(String(32), nullable=False, index=True)
    baseline_commit = Column(String(64), nullable=False)
    candidate_commit = Column(String(64), nullable=True)
    candidate_id = Column(String(64), nullable=True)
    evidence_status = Column(String(32), nullable=False, index=True)
    recommendation = Column(String(32), nullable=False, index=True)
    calculation_version = Column(String(16), nullable=False, default="1.0.0")
    payload = Column(JSON_TYPE, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
        index=True,
    )
