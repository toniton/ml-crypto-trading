import unittest
from unittest.mock import MagicMock
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.trading.session.in_memory_trading_journal import InMemoryTradingJournal


class TestInMemoryTradingJournal(unittest.TestCase):
    def setUp(self):
        self.journal = InMemoryTradingJournal()

    def test_record_fill_adds_completed_order(self):
        order = MagicMock(spec=Order)
        order.status = OrderStatus.COMPLETED
        order.uuid = "123"
        order.ticker_symbol = "BTC"

        self.journal.record_fill(order)

        self.assertEqual(len(self.journal.entries()), 1)
        self.assertEqual(self.journal.entries()[0].uuid, "123")

    def test_record_fill_ignores_incomplete_order(self):
        order = MagicMock(spec=Order)
        order.status = OrderStatus.PENDING
        order.uuid = "124"
        order.ticker_symbol = "BTC"

        self.journal.record_fill(order)

        self.assertEqual(len(self.journal.entries()), 0)

    def test_entries_returns_copy(self):
        order = MagicMock(spec=Order)
        order.status = OrderStatus.COMPLETED
        order.uuid = "125"
        order.ticker_symbol = "BTC"

        self.journal.record_fill(order)
        entries = self.journal.entries()
        entries.clear()

        self.assertEqual(len(self.journal.entries()), 1)

    def test_entries_filters_by_ticker_symbol(self):
        order1 = MagicMock(spec=Order)
        order1.status = OrderStatus.COMPLETED
        order1.uuid = "1"
        order1.ticker_symbol = "BTC"

        order2 = MagicMock(spec=Order)
        order2.status = OrderStatus.COMPLETED
        order2.uuid = "2"
        order2.ticker_symbol = "ETH"

        self.journal.record_fill(order1)
        self.journal.record_fill(order2)

        btc_entries = self.journal.entries(ticker_symbol="BTC")
        eth_entries = self.journal.entries(ticker_symbol="ETH")
        all_entries = self.journal.entries()

        self.assertEqual(len(btc_entries), 1)
        self.assertEqual(btc_entries[0].ticker_symbol, "BTC")
        self.assertEqual(len(eth_entries), 1)
        self.assertEqual(eth_entries[0].ticker_symbol, "ETH")
        self.assertEqual(len(all_entries), 2)

    def test_record_fill_is_idempotent(self):
        order = MagicMock(spec=Order)
        order.status = OrderStatus.COMPLETED
        order.uuid = "123"
        order.ticker_symbol = "BTC"

        self.journal.record_fill(order)
        self.journal.record_fill(order)

        self.assertEqual(len(self.journal.entries()), 1)
