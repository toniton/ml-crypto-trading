from __future__ import annotations

import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


def make_db_manager(db_path: str) -> SqlAlchemyDatabaseManager:
    """Build a SqlAlchemyDatabaseManager backed by a file-based SQLite engine (thread-safe)."""
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = SqlAlchemyDatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr


def make_temp_db_manager() -> SqlAlchemyDatabaseManager:
    """Build a SqlAlchemyDatabaseManager backed by a fresh temporary SQLite file."""
    return make_db_manager(os.path.join(tempfile.mkdtemp(), "test.db"))
