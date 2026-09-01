from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text, func

from src.database.database_manager import DatabaseManager


class MetricDefinitionDao(DatabaseManager.BaseTableModel):
    __tablename__ = "metric_definitions"

    id = Column(String(32), primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    metric_type = Column(String(16), nullable=False)
    unit = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    aggregation = Column(String(16), nullable=True)
    retention_seconds = Column(BigInteger, nullable=False, default=30 * 24 * 3600)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # pylint: disable=not-callable
