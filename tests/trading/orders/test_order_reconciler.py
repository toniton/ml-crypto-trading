import time
import unittest
from unittest.mock import MagicMock

from src.trading.orders.order_reconciler import OrderReconciler


class TestOrderReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_order_manager = MagicMock()
        self.reconciler = OrderReconciler(self.mock_order_manager)
        self.reconciler.RECONCILE_INTERVAL_SECONDS = 0.05

    def tearDown(self):
        self.reconciler.stop()

    def test_start_stop_lifecycle(self):
        self.reconciler.start()
        self.assertIsNotNone(self.reconciler._thread)
        self.assertTrue(self.reconciler._thread.is_alive())

        self.reconciler.stop()
        self.assertFalse(self.reconciler._thread.is_alive())

    def test_trigger_calls_reconcile(self):
        self.reconciler.start()
        self.reconciler.trigger()

        deadline = time.time() + 1
        while self.mock_order_manager.reconcile_pending_orders.call_count == 0 and time.time() < deadline:
            time.sleep(0.01)

        self.assertGreaterEqual(self.mock_order_manager.reconcile_pending_orders.call_count, 1)

    def test_reconcile_exception_keeps_thread_alive(self):
        self.mock_order_manager.reconcile_pending_orders.side_effect = RuntimeError("boom")
        self.reconciler.start()
        self.reconciler.trigger()

        time.sleep(0.2)
        self.assertTrue(self.reconciler._thread.is_alive())
