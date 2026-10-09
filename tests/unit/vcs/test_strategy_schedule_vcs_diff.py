from __future__ import annotations

# pylint: disable=redefined-outer-name,protected-access
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


def test_vcs_diff_strategy_weight_change(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_v1 = {
        "assets": [
            {
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "strategies": [
                    {
                        "name": "Momentum",
                        "action": "BUY",
                        "enabled": True,
                        "weight": 1.0,
                    }
                ],
            }
        ]
    }

    config_v2 = {
        "assets": [
            {
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "strategies": [
                    {
                        "name": "Momentum",
                        "action": "BUY",
                        "enabled": True,
                        "weight": 0.5,
                    }
                ],
            }
        ]
    }

    c1 = vcs.commit(config_v1, "author", "Initial weight")
    c2 = vcs.commit(config_v2, "author", "Reduce weight")

    diffs = vcs.diff(c1.hash, c2.hash)
    assert len(diffs) == 1
    assert diffs[0].path == "assets.BTC_USD.strategies.Momentum.weight"
    assert diffs[0].old_value == 1.0
    assert diffs[0].new_value == 0.5


def test_vcs_diff_strategy_schedule_change(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_v1 = {
        "assets": [
            {
                "base_ticker_symbol": "ETH",
                "quote_ticker_symbol": "USD",
                "strategies": [
                    {
                        "name": "RsiBuy",
                        "action": "BUY",
                        "enabled": True,
                        "weight": 1.0,
                        "schedule": {
                            "timezone": "Europe/Stockholm",
                            "windows": [
                                {
                                    "days": [0, 1, 2, 3, 4],
                                    "start_time": "09:00:00",
                                    "end_time": "16:00:00",
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }

    config_v2 = {
        "assets": [
            {
                "base_ticker_symbol": "ETH",
                "quote_ticker_symbol": "USD",
                "strategies": [
                    {
                        "name": "RsiBuy",
                        "action": "BUY",
                        "enabled": True,
                        "weight": 1.0,
                        "schedule": {
                            "timezone": "America/New_York",
                            "windows": [
                                {
                                    "days": [0, 1, 2, 3, 4],
                                    "start_time": "09:30:00",
                                    "end_time": "16:00:00",
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }

    c1 = vcs.commit(config_v1, "author", "Stockholm schedule")
    c2 = vcs.commit(config_v2, "author", "NY schedule")

    diffs = vcs.diff(c1.hash, c2.hash)
    paths = {d.path for d in diffs}
    assert "assets.ETH_USD.strategies.RsiBuy.schedule.timezone" in paths
    assert "assets.ETH_USD.strategies.RsiBuy.schedule.windows" in paths
