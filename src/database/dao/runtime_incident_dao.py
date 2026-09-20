from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class RuntimeIncidentDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "runtime_incidents"

    id = Column(String(36), primary_key=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    component = Column(String(128), nullable=False)
    operation = Column(String(128), nullable=True)
    asset = Column(String(64), nullable=True, index=True)
    exchange = Column(String(64), nullable=True, index=True)
    commit_hash = Column(String(64), nullable=True)
    first_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # pylint: disable=not-callable
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # pylint: disable=not-callable
    occurrence_count = Column(Integer, nullable=False, default=1)
    diagnosis = Column(JSON_TYPE, nullable=True)
    suggestion = Column(JSON_TYPE, nullable=True)
    notes = Column(Text, nullable=True)

    error_events = relationship(
        "RuntimeErrorEventDao",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="desc(RuntimeErrorEventDao.timestamp)",
    )


class RuntimeErrorEventDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "runtime_error_events"

    id = Column(String(36), primary_key=True)
    incident_id = Column(
        String(36),
        ForeignKey("runtime_incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)  # pylint: disable=not-callable
    severity = Column(String(16), nullable=False)
    component = Column(String(128), nullable=False)
    error_type = Column(String(128), nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    operation = Column(String(128), nullable=True)
    asset = Column(String(64), nullable=True)
    order_id = Column(String(64), nullable=True)
    exchange = Column(String(64), nullable=True)
    exchange_code = Column(Integer, nullable=True)
    http_status = Column(Integer, nullable=True)
    commit_hash = Column(String(64), nullable=True)
    metadata_payload = Column(JSON_TYPE, nullable=True)
    fingerprint = Column(String(64), nullable=False, index=True)

    incident = relationship("RuntimeIncidentDao", back_populates="error_events")
