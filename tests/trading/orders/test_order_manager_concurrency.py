import threading
import time
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction, OrderStatus
from database.database_manager import DatabaseManager
from database.unit_of_work import UnitOfWork
from src.trading.orders.order_manager import OrderManager

from src.core.interfaces.trading_journal import TradingJournal


class TestOrderManagerConcurrency(unittest.TestCase):
    # pylint: disable=protected-access
    def setUp(self):
        self.mock_db_manager = MagicMock(spec=DatabaseManager)
        self.mock_uow = MagicMock(spec=UnitOfWork)
        self.mock_db_manager.get_unit_of_work.return_value = self.mock_uow
        self.mock_uow.__enter__.return_value = self.mock_uow
        self.mock_journal = MagicMock(spec=TradingJournal)
        self.order_manager = OrderManager(self.mock_db_manager, self.mock_journal)

    def tearDown(self):
        if hasattr(self, 'order_manager'):
            self.order_manager.shutdown()

    def test_save_orders_uses_isolated_unit_of_work(self):
        orders = [
            Order(uuid="1", price="100", quantity="1", provider_name="p1",
                  trade_action=TradeAction.BUY, ticker_symbol="BTC", created_time=time.time())
        ]

        def save_orders():
            self.order_manager._save_orders_to_database(orders)

        threads = [threading.Thread(target=save_orders) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(self.mock_db_manager.get_unit_of_work.call_count, 5)
        self.assertEqual(self.mock_uow.__enter__.call_count, 5)
        self.assertEqual(self.mock_uow.__exit__.call_count, 5)
        # Assuming defaults in Order are PENDING, so record_fill should NOT be called.
        self.mock_journal.record_fill.assert_not_called()

    def test_save_orders_updates_journal_for_completed_order(self):
        order = Order(uuid="2", price="101", quantity="1", provider_name="p1",
                      trade_action=TradeAction.BUY, ticker_symbol="BTC", created_time=time.time(),
                      status=OrderStatus.COMPLETED)

        self.order_manager._save_orders_to_database([order])

        self.mock_journal.record_fill.assert_called_once_with(order)

    def test_execute_order_uses_isolated_unit_of_work(self):
        mock_client = MagicMock()
        mock_client.get_provider_name.return_value = "p1"
        self.order_manager.register_client(mock_client)

        order = Order(uuid="3", price="102", quantity="1", provider_name="p1",
                      trade_action=TradeAction.BUY, ticker_symbol="BTC", created_time=time.time())

        self.order_manager.execute_order(order)

        self.assertEqual(self.mock_db_manager.get_unit_of_work.call_count, 1)
        self.assertTrue(self.mock_uow.__enter__.called)
        self.assertTrue(self.mock_uow.__exit__.called)

    def test_get_closing_orders_uses_isolated_unit_of_work(self):
        self.order_manager._get_pending_orders()

        self.assertEqual(self.mock_db_manager.get_unit_of_work.call_count, 1)
        self.assertTrue(self.mock_uow.__enter__.called)
        self.assertTrue(self.mock_uow.__exit__.called)

    def test_cancel_order_calls_provider(self):
        mock_client = MagicMock()
        mock_client.get_provider_name.return_value = "p1"
        self.order_manager.register_client(mock_client)

        order = Order(uuid="4", price="103", quantity="1", provider_name="p1",
                      trade_action=TradeAction.BUY, ticker_symbol="BTC", created_time=time.time())

        self.order_manager._cancel_order(order)
        mock_client.cancel_order.assert_called_once_with(order.uuid)

    def test_shutdown_stops_thread(self):
        # Allow thread to start
        time.sleep(0.1)
        self.assertTrue(self.order_manager._execute_thread.is_alive())

        self.order_manager.shutdown()

        self.assertTrue(self.order_manager._stop_event.is_set())
        self.assertFalse(self.order_manager._execute_thread.is_alive())
