import pytest
from src.configuration.trading_config import TradingConfig
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.server.services.backtest_service import BacktestService
from src.vcs.application.service import VCSService


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = SqlAlchemyDatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr


@pytest.fixture
def initial_config():
    return {
        "dynamic_quantity": "0.01",
        "assets": [
            {
                "name": "Bitcoin",
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "exchange": "CRYPTO_DOT_COM",
                "min_quantity": 0.001,
                "quote_decimals": 2,
                "quantity_decimals": 4,
                "candles_timeframe": "MIN1",
                "schedule": 1,
                "strategies": [
                    {
                        "name": "RSI",
                        "type": "DYNAMIC",
                        "action": "BUY",
                        "expression": "rsi(14) < 30",
                        "enabled": True,
                    }
                ],
                "consensus": {"buy": 1.0, "sell": 0.5},
            }
        ],
    }


def test_backtest_branch_lifecycle_and_merge(in_memory_db, initial_config):
    vcs = VCSService(in_memory_db)
    service = BacktestService(in_memory_db)

    # 1. Seed main branch
    main_commit = vcs.commit(
        TradingConfig.model_validate(initial_config),
        author="system",
        message="Initial main configuration",
        ref="refs/heads/main",
    )
    vcs.commit(
        TradingConfig.model_validate(initial_config),
        author="system",
        message="Seed HEAD",
        ref="HEAD",
    )

    # 2. Create backtest branch
    branch_info = service.create_branch(
        name="BTC Conservative Strategy",
        description="Testing higher consensus threshold",
        source_commit_hash=main_commit.hash,
    )
    branch_id = branch_info["branch_id"]
    assert branch_id.startswith("bt-")
    assert branch_info["head_commit_hash"] == main_commit.hash

    # 3. List branches
    branches = service.list_branches()
    assert len(branches) == 1
    assert branches[0]["branch_id"] == branch_id

    # 4. Edit BTC configuration on backtest branch
    updated_asset = {
        **initial_config["assets"][0],
        "consensus": {"buy": 0.75, "sell": 0.4},
    }
    commit_res = service.update_asset_configuration(
        branch_id=branch_id,
        asset_symbol="BTC_USD",
        asset_data=updated_asset,
        message="Tighten BTC consensus thresholds",
    )
    assert commit_res["commit_hash"] != main_commit.hash

    # Verify main remained untouched
    main_cfg = vcs.checkout("refs/heads/main")
    assert main_cfg["assets"][0]["consensus"]["buy"] == 1.0

    # Verify backtest branch updated
    bt_cfg = service.get_configuration(branch_id)
    assert bt_cfg["assets"][0]["consensus"]["buy"] == 0.75

    # 5. Preview merge into main
    preview = service.preview_merge(branch_id)
    assert preview.status.value in ("CLEAN", "FAST_FORWARD")
    assert len(preview.conflicts) == 0

    # 6. Execute merge into main
    merge_res = service.execute_merge(
        branch_id=branch_id,
        author="trader",
        message="Merge BTC Conservative Strategy into main",
    )
    assert merge_res.status == "MERGED"
    assert len(merge_res.parents) == 2

    # Verify main now has the merged consensus
    new_main_cfg = vcs.checkout("refs/heads/main")
    assert new_main_cfg["assets"][0]["consensus"]["buy"] == 0.75
