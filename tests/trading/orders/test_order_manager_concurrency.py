import threading
import time
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from database.database_manager import DatabaseManager
from database.unit_of_work import UnitOfWork
from src.trading.orders.order_manager import OrderManager


class TestOrderManagerConcurrency(unittest.TestCase):
    # pylint: disable=protected-access
    def setUp(self):
        self.mock_db_manager = MagicMock(spec=DatabaseManager)
        self.mock_uow = MagicMock(spec=UnitOfWork)
        self.mock_db_manager.get_unit_of_work.return_value = self.mock_uow
        self.mock_uow.__enter__.return_value = self.mock_uow
        self.order_manager = OrderManager(self.mock_db_manager)

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
        self.order_manager.get_closing_orders("BTC", "50000")

        self.assertEqual(self.mock_db_manager.get_unit_of_work.call_count, 1)
        self.assertTrue(self.mock_uow.__enter__.called)
        self.assertTrue(self.mock_uow.__exit__.called)

    def test_cancel_order_calls_provider(self):
        mock_client = MagicMock()
        mock_client.get_provider_name.return_value = "p1"
        self.order_manager.register_client(mock_client)

        order = Order(uuid="4", price="103", quantity="1", provider_name="p1",
                      trade_action=TradeAction.BUY, ticker_symbol="BTC", created_time=time.time())

        self.order_manager.cancel_order(order)
        mock_client.cancel_order.assert_called_once_with(order.uuid)

    def test_shutdown_stops_thread(self):
        # Mock the execute thread to avoid starting a real one if needed,
        # but here we test the real one's shutdown if it's already running.
        mock_thread = MagicMock()
        self.order_manager._execute_thread = mock_thread
        mock_thread.is_alive.return_value = True

        self.order_manager.shutdown()

        self.assertTrue(self.order_manager._stop_event.is_set())
        mock_thread.join.assert_called_once()
