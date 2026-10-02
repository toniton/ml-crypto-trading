from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.configuration.llm_config import LlmConfig
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.llm.llm_runtime_manager import LlmRuntimeManager
from src.recorder.market_data_store import MarketDataStore
from src.trading.local_trading_engine_proxy import LocalTradingEngineProxy


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


def make_test_trading_proxy(
        trading_engine=None,
        managers=None,
        market_data_store=None,
        compare_backtest=None,
) -> LocalTradingEngineProxy:
    return LocalTradingEngineProxy(
        trading_engine=trading_engine or MagicMock(),
        managers=managers or MagicMock(),
        market_data_store=market_data_store or MarketDataStore(),
        compare_backtest=compare_backtest or (lambda action: None),
    )


def make_test_llm_manager(db_manager) -> LlmRuntimeManager:
    return LlmRuntimeManager(llm_config=LlmConfig(), db_manager=db_manager)
