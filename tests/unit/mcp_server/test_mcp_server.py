from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database_manager import DatabaseManager
from src.configuration.trading_config import TradingConfig
from vcs.application.service import VCSService


def _parse(result) -> dict:
    if isinstance(result, list):
        return json.loads(result[0].text)
    return json.loads(result.content[0].text)


def _checkout_config(vcs) -> TradingConfig:
    return TradingConfig.model_validate(vcs.checkout("HEAD"))


@pytest.fixture
def mock_db_manager():
    """Creates an in-memory SQLite DatabaseManager for testing VCS operations."""
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


@pytest.fixture
def config_vcs(mock_db_manager):
    vcs = VCSService(mock_db_manager)
    initial_config = {
        "assets": [
            {
                "name": "Bitcoin",
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "exchange": "CRYPTO_DOT_COM",
                "min_quantity": 0.00005,
                "quote_decimals": 5,
                "quantity_decimals": 5,
                "candles_timeframe": "MIN1",
                "schedule": 1,
            }
        ],
        "consensus": {"buy": 1.3, "sell": 0.5},
        "dynamic_quantity": "min_qty",
    }
    vcs.commit(initial_config, author="test", message="Initial config")
    return vcs


@pytest.fixture
def config_server(config_vcs):
    from mcp_server.server import TradingConfigMCPServer

    return TradingConfigMCPServer(vcs=config_vcs)


class TestGetTradingConfig:
    def test_returns_consensus_and_dynamic_quantity(self, config_server):
        import anyio

        raw = anyio.run(config_server.mcp.call_tool, "get_trading_config", {})
        result = _parse(raw)

        assert result["consensus"]["buy"] == 1.3
        assert result["consensus"]["sell"] == 0.5
        assert result["dynamic_quantity"] == "min_qty"

    def test_does_not_return_assets(self, config_server):
        import anyio

        result = _parse(anyio.run(config_server.mcp.call_tool, "get_trading_config", {}))

        assert "assets" not in result

    def test_empty_store_raises_clear_error(self, mock_db_manager):
        import anyio
        from mcp_server.server import TradingConfigMCPServer

        empty_vcs = VCSService(mock_db_manager)
        empty_server = TradingConfigMCPServer(vcs=empty_vcs)

        with pytest.raises(Exception, match="No configuration has been committed"):
            anyio.run(empty_server.mcp.call_tool, "get_trading_config", {})


class TestUpdateConsensus:
    def test_updates_buy_and_sell(self, config_vcs, config_server):
        import anyio

        anyio.run(config_server.mcp.call_tool, "update_consensus", {"buy": 2.0, "sell": 0.8})

        config = _checkout_config(config_vcs)
        assert config.consensus.buy == 2.0
        assert config.consensus.sell == 0.8

    def test_returns_updated_values(self, config_server):
        import anyio

        result = _parse(anyio.run(config_server.mcp.call_tool, "update_consensus", {"buy": 1.5, "sell": 0.6}))

        assert result["updated"]["consensus"]["buy"] == 1.5
        assert result["updated"]["consensus"]["sell"] == 0.6

    def test_rejects_buy_less_than_zero(self, config_server):
        import anyio

        with pytest.raises(Exception, match="buy must be > 0"):
            anyio.run(config_server.mcp.call_tool, "update_consensus", {"buy": -1.0, "sell": 0.5})

    def test_rejects_sell_greater_than_buy(self, config_server):
        import anyio

        with pytest.raises(Exception, match="sell .* must be <= buy"):
            anyio.run(config_server.mcp.call_tool, "update_consensus", {"buy": 0.5, "sell": 1.0})

    def test_preserves_other_config_fields(self, config_vcs, config_server):
        import anyio

        anyio.run(config_server.mcp.call_tool, "update_consensus", {"buy": 2.0, "sell": 0.8})

        config = _checkout_config(config_vcs)
        assert config.assets[0].name == "Bitcoin"
        assert config.dynamic_quantity == "min_qty"


class TestUpdateDynamicQuantity:
    def test_updates_formula(self, config_vcs, config_server):
        import anyio

        formula = "max(min_qty, equity * 0.05 / close)"
        anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": formula})

        config = _checkout_config(config_vcs)
        assert config.dynamic_quantity == formula

    def test_returns_updated_formula(self, config_server):
        import anyio

        formula = "equity * 0.1"
        result = _parse(anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": formula}))

        assert result["updated"]["dynamic_quantity"] == formula

    def test_empty_formula_sets_none(self, config_vcs, config_server):
        import anyio

        anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": ""})

        config = _checkout_config(config_vcs)
        assert config.dynamic_quantity is None

    def test_preserves_consensus_on_formula_update(self, config_vcs, config_server):
        import anyio

        anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": "min_qty * 2"})

        config = _checkout_config(config_vcs)
        assert config.consensus.buy == 1.3
        assert config.consensus.sell == 0.5

    def test_rejects_too_long_formula(self, config_server):
        import anyio

        formula = "min_qty + " + "1 " * 500

        with pytest.raises(Exception, match="must be at most 1000 characters"):
            anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": formula})

    def test_accepts_complex_formula(self, config_vcs, config_server):
        import anyio

        formula = (
            "max(min_qty, min((equity * risk_pct / close) * signal * "
            "(1.5 if rsi(14) > 60 else 1) * (1.5 if pnl > 0 else 0.5), "
            "equity * 0.1 / close))"
        )
        anyio.run(config_server.mcp.call_tool, "update_dynamic_quantity", {"formula": formula})

        config = _checkout_config(config_vcs)
        assert config.dynamic_quantity == formula
