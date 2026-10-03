from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.vcs.application.service import VCSService


@pytest.fixture
def mock_db_manager():
    engine = create_engine("sqlite:///:memory:")
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = SqlAlchemyDatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    return db_mgr


def test_vcs_diff_between_commits(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_v1 = {
        "dynamic_quantity": "10",
        "assets": [
            {
                "base_ticker_symbol": "CRO",
                "quote_ticker_symbol": "USD",
                "schedule": 1,
                "consensus": {"buy": 1.3, "sell": 0.5},
                "guard_config": {"drawdown_limit": 0.1},
                "strategies": [
                    {"name": "RsiOversoldBuy", "action": "BUY", "enabled": True}
                ],
            }
        ],
    }

    config_v2 = {
        "dynamic_quantity": "20",
        "assets": [
            {
                "base_ticker_symbol": "CRO",
                "quote_ticker_symbol": "USD",
                "schedule": 2,
                "consensus": {"buy": 1.15, "sell": 0.5},
                "guard_config": {"drawdown_limit": 0.15},
                "strategies": [
                    {"name": "RsiOversoldBuy", "action": "BUY", "enabled": False},
                    {"name": "MacdCross", "action": "BUY", "enabled": True},
                ],
            },
            {
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "schedule": 1,
            },
        ],
    }

    c1 = vcs.commit(config_v1, author="test", message="Base commit", ref="HEAD")
    c2 = vcs.commit(config_v2, author="test", message="Update CRO and add BTC", ref="HEAD")

    diff = vcs.diff(c1.hash, c2.hash)
    paths = {ch.path: ch for ch in diff}

    assert "dynamic_quantity" in paths
    assert paths["dynamic_quantity"].old_value == "10"
    assert paths["dynamic_quantity"].new_value == "20"

    assert "assets.CRO_USD.schedule" in paths
    assert paths["assets.CRO_USD.schedule"].old_value == 1
    assert paths["assets.CRO_USD.schedule"].new_value == 2

    assert "assets.CRO_USD.consensus.buy" in paths
    assert paths["assets.CRO_USD.consensus.buy"].old_value == 1.3
    assert paths["assets.CRO_USD.consensus.buy"].new_value == 1.15

    assert "assets.CRO_USD.guard_config.drawdown_limit" in paths
    assert paths["assets.CRO_USD.guard_config.drawdown_limit"].old_value == 0.1
    assert paths["assets.CRO_USD.guard_config.drawdown_limit"].new_value == 0.15

    assert "assets.CRO_USD.strategies.RsiOversoldBuy.enabled" in paths
    assert paths["assets.CRO_USD.strategies.RsiOversoldBuy.enabled"].old_value is True
    assert paths["assets.CRO_USD.strategies.RsiOversoldBuy.enabled"].new_value is False

    assert "assets.CRO_USD.strategies.MacdCross" in paths
    assert paths["assets.CRO_USD.strategies.MacdCross"].old_value is None
    assert paths["assets.CRO_USD.strategies.MacdCross"].new_value["name"] == "MacdCross"

    assert "assets.BTC_USD" in paths
    assert paths["assets.BTC_USD"].old_value is None
    assert paths["assets.BTC_USD"].new_value["base_ticker_symbol"] == "BTC"
