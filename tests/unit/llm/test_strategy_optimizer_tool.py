from datetime import datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.database_manager import DatabaseManager
from src.llm.tools.strategy_optimizer_tool import StrategyOptimizerTool


class TestStrategyOptimizerTool(unittest.TestCase):
    def _make_order(self, uuid="o1", action=TradeAction.BUY, price="100.0", qty="1.0", strategy="TrendFollower"):
        return Order(
            uuid=uuid,
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal(price),
            fill_price=Decimal(price),
            quantity=qty,
            trade_action=action,
            status=OrderStatus.COMPLETED,
            created_time=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc).timestamp(),
            executed_time=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc).timestamp(),
            fees=Decimal("0.10"),
            winning_strategy=strategy,
            strategy_attributions={strategy: 1.0},
        )

    def _setup_mock_db(self, orders):
        db_manager = MagicMock(spec=DatabaseManager)
        uow = MagicMock()
        repo = MagicMock()
        repo.get_completed_by_ticker_and_executed_range.return_value = orders
        repo.get_completed_by_executed_range.return_value = orders
        uow.get_repository.return_value = repo
        uow.__enter__.return_value = uow
        uow.__exit__.return_value = None
        db_manager.get_unit_of_work.return_value = uow
        return db_manager

    def test_no_trades_found(self):
        db = self._setup_mock_db([])
        tool = StrategyOptimizerTool(database_manager=db)
        result = tool._run(action="calibrate", ticker_symbol="BTC_USD")
        self.assertIn("No historical trades found", result)

    def test_calibrate_action(self):
        orders = []
        for i in range(4):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        tool = StrategyOptimizerTool(database_manager=db)
        result = tool._run(action="calibrate", ticker_symbol="BTC_USD")
        self.assertIn("Strategy Weight Calibration", result)
        self.assertIn("TrendFollower", result)

    def test_windows_action(self):
        orders = []
        for i in range(3):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        tool = StrategyOptimizerTool(database_manager=db)
        result = tool._run(action="windows", ticker_symbol="BTC_USD")
        self.assertIn("Recommended Trading Windows", result)

    def test_redundancy_action(self):
        orders = [
            self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0"),
            self._make_order(uuid="s1", action=TradeAction.SELL, price="110.0"),
        ]
        db = self._setup_mock_db(orders)
        tool = StrategyOptimizerTool(database_manager=db)
        result = tool._run(action="redundancy", ticker_symbol="BTC_USD")
        self.assertTrue("redundancy" in result.lower() or "no high-redundancy" in result.lower())

    def test_proposal_action(self):
        orders = []
        for i in range(4):
            buy = self._make_order(uuid=f"b{i}", action=TradeAction.BUY, price="100.0")
            sell = self._make_order(uuid=f"s{i}", action=TradeAction.SELL, price="115.0")
            orders.extend([buy, sell])

        db = self._setup_mock_db(orders)
        tool = StrategyOptimizerTool(database_manager=db)
        result = tool._run(action="proposal", ticker_symbol="BTC_USD")
        self.assertIn("Optimization Proposal Generated", result)
