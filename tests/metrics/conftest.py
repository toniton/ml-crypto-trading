import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.database_manager import DatabaseManager


@pytest.fixture
def db_manager():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr
