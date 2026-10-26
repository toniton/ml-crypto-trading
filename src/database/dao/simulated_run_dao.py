from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class SimulatedRunDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "simulated_runs"

    id = Column(String(64), primary_key=True)
    experiment_id = Column(String(64), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    candidate_commit = Column(String(64), nullable=False)
    config_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="SIMULATION_QUEUED", index=True)
    market_data_spec = Column(JSON_TYPE, nullable=False)
    execution_spec = Column(JSON_TYPE, nullable=False)
    error_message = Column(Text, nullable=True)
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
