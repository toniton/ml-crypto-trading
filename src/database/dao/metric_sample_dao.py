from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from src.database.dao.blob_dao import JSON_TYPE
from src.database.database_manager import DatabaseManager


class MetricSampleDao(DatabaseManager.BaseTableModel):
    __tablename__ = "metric_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_id = Column(String(32), ForeignKey("metric_definitions.id"), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    value = Column(Float, nullable=False)
    labels = Column(JSON_TYPE, nullable=False, default=dict)
