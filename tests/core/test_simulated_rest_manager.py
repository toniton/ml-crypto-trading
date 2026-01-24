import unittest
from decimal import Decimal

from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.simulation.simulated_account import SimulatedAccount
from src.core.simulation.simulated_rest_manager import SimulatedRestManager


class TestSimulatedRestManager(unittest.TestCase):
    def setUp(self):
        self.initial_balance = Decimal("100000.0")
        self.account = SimulatedAccount(self.initial_balance)
        self.manager = SimulatedRestManager(self.account)

    def test_get_account_balance(self):
        # Default USD balance
        balances = self.manager.get_account_balance("BINANCE")
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0].currency, "USD")
        self.assertEqual(balances[0].available_balance, self.initial_balance)

        # Update balance manually to test reflection
        self.account.set_balance("BTC", Decimal("1.5"))
        balances = self.manager.get_account_balance("BINANCE")
        self.assertEqual(len(balances), 2)
        btc_balance = next(b for b in balances if b.currency == "BTC")
        self.assertEqual(btc_balance.available_balance, Decimal("1.5"))

    def test_place_order(self):
        uuid = "order-123"
        self.manager.place_order(
            exchange="BINANCE",
            uuid=uuid,
            ticker_symbol="BTC/USD",
            quantity="1.0",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY
        )

        order = self.manager.get_order("BINANCE", uuid)
        self.assertIsNotNone(order)
        self.assertEqual(order.uuid, uuid)
        self.assertEqual(order.ticker_symbol, "BTC/USD")
        self.assertEqual(order.quantity, "1.0")
        self.assertEqual(order.price, Decimal("50000.0"))
        self.assertEqual(order.trade_action, TradeAction.BUY)
        # Check if status is COMPLETED (the simulated manager executes immediately)
        self.assertEqual(order.status, OrderStatus.COMPLETED)

    def test_cancel_order(self):
        uuid = "order-to-cancel"
        self.manager.place_order(
            exchange="BINANCE",
            uuid=uuid,
            ticker_symbol="BTC/USD",
            quantity="1.0",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY
        )

        # Verify it exists
        order = self.manager.get_order("BINANCE", uuid)
        self.assertIsNotNone(order)

        # Cancel
        self.manager.cancel_order("BINANCE", uuid)

        # In current SimulatedAccount implementation, cancel doesn't remove it or change status explicitly
        # but the method should run without error.
        # Ideally we'd test side effects if SimulatedAccount had them.
        # For now, just ensuring no crash.

    def test_fees_are_zero(self):
        fees = self.manager.get_account_fees("BINANCE")
        self.assertEqual(fees.maker_fee_pct, Decimal("0.0"))
        self.assertEqual(fees.taker_fee_pct, Decimal("0.0"))

        fees = self.manager.get_instrument_fees("BINANCE", "BTC/USD")
        self.assertEqual(fees.maker_fee_pct, Decimal("0.0"))
        self.assertEqual(fees.taker_fee_pct, Decimal("0.0"))
