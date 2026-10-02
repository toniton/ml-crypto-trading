from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, func

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class LlmCredentialDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "llm_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, unique=True, index=True, nullable=False)
    provider = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    api_base_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False  # pylint: disable=not-callable
    )
    last_updated_timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        onupdate=func.now(),  # pylint: disable=not-callable
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_llm_credentials_active",
            "is_active",
            unique=True,
            postgresql_where=(Column("is_active").is_(True)),
        ),
    )
