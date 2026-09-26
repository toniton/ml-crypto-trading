from datetime import datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.database_manager import DatabaseManager
from src.llm.tools.trade_attribution_tool import TradeAttributionTool


class TestTradeAttributionTool(unittest.TestCase):
    def _make_order(self, uuid="o1", action=TradeAction.BUY, price="100.0", qty="1.0", strategy="RsiOversold", commit="c0ffee"):
        return Order(
            uuid=uuid,
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal(price),
            fill_price=Decimal(price),
            quantity=qty,
            trade_action=action,
            status=OrderStatus.COMPLETED,
            created_time=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp(),
            executed_time=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp(),
            fees=Decimal("0.10"),
            winning_strategy=strategy,
            commit_hash=commit,
        )

    def _setup_mock_db(self, orders):
        db_manager = MagicMock(spec=DatabaseManager)
        uow = MagicMock()
        repo = MagicMock()
        repo.get_completed_by_ticker_and_executed_range.return_value = orders
        repo.get_all.return_value = orders
        uow.get_repository.return_value = repo
        uow.__enter__.return_value = uow
        uow.__exit__.return_value = None
        db_manager.get_unit_of_work.return_value = uow
        return db_manager

    def test_no_trades_found(self):
        db = self._setup_mock_db([])
        tool = TradeAttributionTool(database_manager=db)
        result = tool._run(dimension="strategy", ticker_symbol="BTC_USD")
        self.assertIn("No completed trades found", result)

    def test_strategy_attribution_formatting(self):
        buy = self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0", strategy="RsiOversold")
        sell = self._make_order(uuid="s1", action=TradeAction.SELL, price="120.0", strategy="RsiOversold")
        db = self._setup_mock_db([buy, sell])
        tool = TradeAttributionTool(database_manager=db)
        result = tool._run(dimension="strategy", ticker_symbol="BTC_USD")
        self.assertIn("RsiOversold", result)

    def test_commit_attribution_formatting(self):
        buy = self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0", commit="commit_123")
        sell = self._make_order(uuid="s1", action=TradeAction.SELL, price="120.0", commit="commit_123")
        db = self._setup_mock_db([buy, sell])
        tool = TradeAttributionTool(database_manager=db)
        result = tool._run(dimension="commit", ticker_symbol="BTC_USD")
        self.assertIn("commit_123", result)

    def test_overall_attribution_formatting(self):
        buy = self._make_order(uuid="b1", action=TradeAction.BUY, price="100.0")
        sell = self._make_order(uuid="s1", action=TradeAction.SELL, price="120.0")
        db = self._setup_mock_db([buy, sell])
        tool = TradeAttributionTool(database_manager=db)
        result = tool._run(dimension="overall", ticker_symbol="BTC_USD")
        self.assertIn("Overall Performance", result)
