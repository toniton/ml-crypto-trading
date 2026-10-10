from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade import Trade
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.agent.configuration.configuration_service import ConfigurationService
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.database.repositories.providers.postgres_trade_repository import PostgresTradeRepository
from src.llm.tools.strategy_optimizer_tool import StrategyOptimizerTool


# pylint: disable=protected-access
class TestStrategyOptimizerTool(unittest.TestCase):
    def _make_order(
            self,
            uuid="o1",
            action=TradeAction.BUY,
            price="100.0",
            qty="1.0",
            strategy="TrendFollower",
            timestamp=None,
    ):
        ts = timestamp if timestamp is not None else datetime.now(timezone.utc).timestamp()
        return Order(
            uuid=uuid,
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal(price),
            fill_price=Decimal(price),
            quantity=qty,
            trade_action=action,
            status=OrderStatus.COMPLETED,
            created_time=ts,
            executed_time=ts,
            fees=Decimal("0.10"),
            winning_strategy=strategy,
            strategy_attributions={strategy: 1.0},
        )

    def _setup_mock_db(self, orders, trades=None):
        db_manager = MagicMock(spec=DatabaseManager)
        uow = MagicMock()
        order_repo = MagicMock(spec=PostgresOrderRepository)
        order_repo.get_completed_by_ticker_and_executed_range.return_value = orders
        order_repo.get_completed_by_executed_range.return_value = orders

        trade_repo = MagicMock(spec=PostgresTradeRepository)
        trade_repo.get_by_exit_range.return_value = trades or []

        def get_repository(repo_cls):
            if repo_cls is PostgresTradeRepository:
                return trade_repo
            return order_repo

        uow.get_repository.side_effect = get_repository
        uow.__enter__.return_value = uow
        uow.__exit__.return_value = None
        db_manager.get_unit_of_work.return_value = uow
        return db_manager

    def _setup_mock_config(self, strategies=None, commit_hash="vcs-commit-hash-789"):
        service = MagicMock(spec=ConfigurationService)
        if strategies is None:
            strategies = [{"name": "TrendFollower", "weight": 1.0, "enabled": True}]
        cfg = {
            "name": "Bitcoin",
            "base_ticker_symbol": "BTC",
            "quote_ticker_symbol": "USD",
            "strategies": strategies,
        }
        service.get_asset_config.return_value = cfg
        service.get_asset_config_snapshot.return_value = (cfg, commit_hash)
        service.get_head_commit_hash.return_value = commit_hash
        return service

    def test_no_trades_found(self):
        db = self._setup_mock_db([])
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="calibrate", ticker_symbol="BTC_USD")
        self.assertIn("No historical trades found", result)

    def test_calibrate_action_with_authoritative_config(self):
        orders = []
        for i in range(4):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        config = self._setup_mock_config(
            strategies=[{"name": "TrendFollower", "weight": 1.5, "enabled": True}]
        )
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="calibrate", ticker_symbol="BTC_USD")
        self.assertIn("Strategy Weight Calibration Recommendations for BTC_USD", result)
        self.assertIn("TrendFollower", result)
        self.assertIn("Current=1.50", result)

    def test_calibrate_missing_ticker_symbol(self):
        orders = [
            self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0"),
            self._make_order(uuid="s1", action=TradeAction.SELL, price="115.0"),
        ]
        db = self._setup_mock_db(orders)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="calibrate", ticker_symbol=None)
        self.assertIn("Error: 'ticker_symbol' is required", result)

    def test_calibrate_unconfigured_asset(self):
        orders = [
            self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0"),
            self._make_order(uuid="s1", action=TradeAction.SELL, price="115.0"),
        ]
        db = self._setup_mock_db(orders)
        config = MagicMock(spec=ConfigurationService)
        config.get_asset_config.return_value = None
        config.get_asset_config_snapshot.return_value = (None, None)
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="calibrate", ticker_symbol="UNKNOWN_PAIR")
        self.assertIn("Error: Asset 'UNKNOWN_PAIR' is not configured", result)

    def test_windows_action(self):
        orders = []
        for i in range(3):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="windows", ticker_symbol="BTC_USD")
        self.assertIn("Recommended Trading Windows", result)

    def test_redundancy_action(self):
        orders = [
            self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0"),
            self._make_order(uuid="s1", action=TradeAction.SELL, price="110.0"),
        ]
        db = self._setup_mock_db(orders)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="redundancy", ticker_symbol="BTC_USD")
        self.assertTrue("redundancy" in result.lower() or "no high-redundancy" in result.lower())

    def test_proposal_action_binds_base_commit(self):
        orders = []
        for i in range(4):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        config = self._setup_mock_config(commit_hash="commit-hash-vcs-xyz")
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="proposal", ticker_symbol="BTC_USD")
        self.assertIn("Optimization Proposal Generated for BTC_USD", result)
        self.assertIn("Base Commit", result)
        self.assertIn("commit-hash-vcs-xyz", result)

    def test_fetch_db_trades_pads_history_and_filters_completed(self):
        now = datetime.now(timezone.utc)
        # Entry occurred 40 days ago (outside 30d window), exit occurred 10 days ago (inside 30d window)
        ts_entry = (now - timedelta(days=40)).timestamp()
        ts_exit = (now - timedelta(days=10)).timestamp()
        orders = [
            self._make_order(uuid="b_old", action=TradeAction.BUY, price="100.0", timestamp=ts_entry),
            self._make_order(uuid="s_recent", action=TradeAction.SELL, price="120.0", timestamp=ts_exit),
        ]
        db = self._setup_mock_db(orders)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        trades = tool._gather_trades(ticker_symbol="BTC_USD", lookback_days=30)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].net_pnl, Decimal("19.80"))

    def test_requires_dependencies_at_init(self):
        # pylint: disable=no-value-for-parameter
        with self.assertRaises(TypeError):
            StrategyOptimizerTool()  # Missing both required arguments
        db = self._setup_mock_db([])
        with self.assertRaises(TypeError):
            StrategyOptimizerTool(database_manager=db)  # Missing configuration_service

    def test_fetch_db_trades_prefers_authoritative_persisted_trades(self):
        persisted = [
            Trade.create(
                ticker_symbol="BTC_USD",
                entry_order_uuid="e-persisted",
                exit_order_uuid="x-persisted",
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                quantity=Decimal("1"),
                entry_fee=Decimal("0.1"),
                exit_fee=Decimal("0.1"),
                entry_timestamp=100.0,
                exit_timestamp=200.0,
                winning_strategy="TrendFollower",
            )
        ]
        db = self._setup_mock_db(orders=[], trades=persisted)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        trades = tool._gather_trades(ticker_symbol="BTC_USD", lookback_days=30)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_order_uuid, "e-persisted")

    def test_incomplete_history_warning_emitted_on_unmatched_exits(self):
        now = datetime.now(timezone.utc)
        orders = [
            self._make_order(uuid="s_orphan", action=TradeAction.SELL, price="120.0", timestamp=now.timestamp()),
            self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0", timestamp=now.timestamp()),
            self._make_order(uuid="s1", action=TradeAction.SELL, price="110.0", timestamp=now.timestamp()),
        ]
        db = self._setup_mock_db(orders=orders)
        config = self._setup_mock_config()
        tool = StrategyOptimizerTool(database_manager=db, configuration_service=config)
        result = tool._run(action="calibrate", ticker_symbol="BTC_USD")
        self.assertIn("Incomplete historical lookback detected", result)
