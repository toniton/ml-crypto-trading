import importlib
import pkgutil

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.database.dao as dao_package
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager

for _, module_name, _ in pkgutil.iter_modules(dao_package.__path__):
    importlib.import_module(f"src.database.dao.{module_name}")


@pytest.fixture
def db_manager():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_mgr = SqlAlchemyDatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr
