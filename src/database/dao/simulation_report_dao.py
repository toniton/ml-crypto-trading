from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class SimulationReportDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "simulation_reports"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    config_hash = Column(String(64), nullable=False)
    decision = Column(String(32), nullable=False, index=True)
    summary_metrics = Column(JSON_TYPE, nullable=False)
    report_payload = Column(JSON_TYPE, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
        index=True,
    )
