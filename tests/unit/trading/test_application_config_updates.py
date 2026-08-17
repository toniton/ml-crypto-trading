from __future__ import annotations

from queue import Queue
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.database_manager import DatabaseManager
from src.application import Application
from src.configuration.trading_config import TradingConfig
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.vcs.application.events import RefChangedEvent
from src.vcs.application.service import VCSService


@pytest.fixture
def vcs():
    engine = create_engine("sqlite:///:memory:")
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    return VCSService(db_mgr)


def _seed_config(vcs, consensus=None, dynamic_quantity="min_qty", ref="HEAD", **overrides):
    config = {
        "assets": [],
        "consensus": consensus or {"buy": 1.3, "sell": 0.5},
        "dynamic_quantity": dynamic_quantity,
    }
    config.update(overrides)
    return vcs.commit(config, author="test", message="commit", ref=ref)


class _FakeEngine:
    def __init__(self):
        self.configs = []

    def update_config(self, trading_config):
        self.configs.append(trading_config)


def _make_app(vcs):
    app = object.__new__(Application)
    app._vcs = vcs
    app._vcs_ref = "HEAD"
    app._trading_config = TradingConfig.model_validate(
        {"assets": [], "consensus": {"buy": 1.3, "sell": 0.5}, "dynamic_quantity": "min_qty"}
    )
    app._trading_engine = _FakeEngine()
    return app


class TestEnsureConfigStoreSeeded:
    def test_seeds_empty_store_from_bootstrap_config(self, vcs):
        app = _make_app(vcs)

        app._ensure_config_store_seeded()

        seeded = TradingConfig.model_validate(vcs.checkout("HEAD"))
        assert seeded.consensus.buy == 1.3
        assert seeded.consensus.sell == 0.5
        assert seeded.dynamic_quantity == "min_qty"

    def test_does_not_overwrite_existing_head(self, vcs):
        existing = _seed_config(vcs, consensus={"buy": 1.0, "sell": 0.5})
        app = _make_app(vcs)

        app._ensure_config_store_seeded()

        assert vcs.head("HEAD").hash == existing.hash
        assert TradingConfig.model_validate(vcs.checkout("HEAD")).consensus.buy == 1.0


class TestApplyConfigUpdate:
    def test_hands_checked_out_config_to_engine(self, vcs):
        app = _make_app(vcs)
        commit = _seed_config(vcs, consensus={"buy": 2.0, "sell": 0.8}, dynamic_quantity="equity * 0.1")

        app._apply_config_update(commit.hash)

        applied = app._trading_engine.configs[-1]
        assert applied.consensus.buy == 2.0
        assert applied.consensus.sell == 0.8
        assert applied.dynamic_quantity == "equity * 0.1"

    def test_skips_when_engine_absent(self, vcs):
        app = _make_app(vcs)
        app._trading_engine = None
        commit = _seed_config(vcs, consensus={"buy": 2.0, "sell": 0.8})

        app._apply_config_update(commit.hash)

    def test_missing_commit_is_logged_without_crash(self, vcs):
        app = _make_app(vcs)

        app._apply_config_update("deadbeef" * 8)

        assert app._trading_engine.configs == []


class TestOnRefChange:
    def test_ignores_events_for_other_refs(self, vcs):
        app = _make_app(vcs)
        commit = _seed_config(vcs, consensus={"buy": 2.0, "sell": 0.8}, ref="production")

        app._on_vcs_ref_change(RefChangedEvent(ref="production", commit_hash=commit.hash))

        assert app._trading_engine.configs == []

    def test_applies_events_for_tracked_ref(self, vcs):
        app = _make_app(vcs)
        commit = _seed_config(vcs, consensus={"buy": 2.0, "sell": 0.8})

        app._on_vcs_ref_change(RefChangedEvent(ref="HEAD", commit_hash=commit.hash))

        assert app._trading_engine.configs[-1].consensus.buy == 2.0


class TestTradingEngineUpdateConfig:
    def test_delegates_to_executor(self):
        engine = object.__new__(TradingEngine)
        executor = _FakeEngine()
        engine._trading_executor = executor

        config = TradingConfig.model_validate(
            {"assets": [], "consensus": {"buy": 2.0, "sell": 0.8}, "dynamic_quantity": "equity * 0.1"}
        )
        engine.update_config(config)

        assert executor.configs == [config]


def _make_executor(consensus=None, dynamic_quantity="min_qty"):
    consensus = consensus or ConsensusFactor(buy=1.3, sell=0.5)
    consensus_manager = ConsensusManager(consensus)
    container = SimpleNamespace(
        account_manager=None,
        fees_manager=None,
        order_manager=None,
        market_data_manager=None,
        consensus_manager=consensus_manager,
        session_manager=None,
        protection_manager=None,
        websocket_manager=None,
    )
    executor = TradingExecutor(assets=[], manager_container=container, activity_queue=Queue(), dynamic_quantity=dynamic_quantity)
    return executor


class TestTradingExecutorUpdateConfig:
    def test_applies_consensus_and_dynamic_quantity(self):
        executor = _make_executor()
        config = TradingConfig.model_validate(
            {"assets": [], "consensus": {"buy": 2.0, "sell": 0.8}, "dynamic_quantity": "equity * 0.1"}
        )

        executor.update_config(config)

        assert executor.consensus_manager.consensus_factor.buy == 2.0
        assert executor.consensus_manager.consensus_factor.sell == 0.8
        assert executor._dynamic_quantity == "equity * 0.1"
        assert executor._dynamic_quantity_parser.expression == "equity * 0.1"

    def test_disables_dynamic_quantity_with_none(self):
        executor = _make_executor()
        config = TradingConfig.model_validate(
            {"assets": [], "consensus": {"buy": 1.3, "sell": 0.5}, "dynamic_quantity": None}
        )

        executor.update_config(config)

        assert executor._dynamic_quantity is None
        assert executor._dynamic_quantity_parser is None

    def test_does_not_rebuild_parser_when_formula_unchanged(self):
        executor = _make_executor()
        parser = executor._dynamic_quantity_parser
        config = TradingConfig.model_validate(
            {"assets": [], "consensus": {"buy": 1.3, "sell": 0.5}, "dynamic_quantity": "min_qty"}
        )

        executor.update_config(config)

        assert executor._dynamic_quantity_parser is parser

    def test_does_not_replace_consensus_when_unchanged(self):
        executor = _make_executor()
        factor = executor.consensus_manager.consensus_factor
        config = TradingConfig.model_validate(
            {"assets": [], "consensus": {"buy": 1.3, "sell": 0.5}, "dynamic_quantity": "min_qty"}
        )

        executor.update_config(config)

        assert executor.consensus_manager.consensus_factor is factor
