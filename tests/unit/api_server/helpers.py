from __future__ import annotations

import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.database_manager import DatabaseManager


def make_db_manager(db_path: str) -> DatabaseManager:
    """Build a DatabaseManager backed by a file-based SQLite engine (thread-safe)."""
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr


def make_temp_db_manager() -> DatabaseManager:
    """Build a DatabaseManager backed by a fresh temporary SQLite file."""
    return make_db_manager(os.path.join(tempfile.mkdtemp(), "test.db"))
