import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.trading.protection.guards.reconciliation_guard import (
    ReconciliationGuard,
)
from src.trading.protection.protection_manager import ProtectionManager


class TestReconciliationGuard(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MagicMock()
        self.guard = ReconciliationGuard(reconciliation_engine=self.mock_engine)
        self.trading_context = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("1000"),
        )
        self.mock_market_data = MagicMock()

    def test_can_trade_true_when_no_critical_discrepancy(self):
        self.mock_engine.has_critical_discrepancy.return_value = False
        allowed = self.guard.can_trade(
            TradeAction.BUY, self.trading_context, self.mock_market_data
        )
        self.assertTrue(allowed)

    def test_can_trade_false_when_critical_discrepancy_exists(self):
        self.mock_engine.has_critical_discrepancy.return_value = True
        allowed = self.guard.can_trade(
            TradeAction.BUY, self.trading_context, self.mock_market_data
        )
        self.assertFalse(allowed)

    def test_protection_manager_pause_and_resume(self):
        protection_mgr = ProtectionManager()
        self.assertTrue(protection_mgr.can_trade(1, TradeAction.BUY, self.trading_context, self.mock_market_data))

        protection_mgr.pause_trading("Critical reconciliation error")
        self.assertTrue(protection_mgr.is_paused)
        self.assertFalse(protection_mgr.can_trade(1, TradeAction.BUY, self.trading_context, self.mock_market_data))

        protection_mgr.resume_trading()
        self.assertFalse(protection_mgr.is_paused)
        self.assertTrue(protection_mgr.can_trade(1, TradeAction.BUY, self.trading_context, self.mock_market_data))
