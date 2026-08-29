import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.database_manager import DatabaseManager
from src.server.services.order_latency_service import OrderLatencyService


def order_on(day: str, latency_ms: float, at_hour: int = 10) -> Order:
    created = datetime.fromisoformat(day).replace(hour=at_hour, tzinfo=timezone.utc)
    return Order(
        uuid=str(hash((day, latency_ms, at_hour))),
        provider_name="p1",
        ticker_symbol="BTC",
        price="100",
        quantity="1",
        trade_action=TradeAction.BUY,
        created_time=created.timestamp(),
        executed_time=created.timestamp() + latency_ms / 1000,
        status=OrderStatus.COMPLETED,
    )


class TestOrderLatencyService(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock(spec=DatabaseManager)
        self.uow = MagicMock()
        self.db_manager.get_unit_of_work.return_value = self.uow
        self.uow.__enter__.return_value = self.uow
        self.repo = self.uow.get_repository.return_value
        self.service = OrderLatencyService(self.db_manager)

    def _set_orders(self, orders):
        self.repo.get_by_date_range.return_value = orders

    def _days(self, result):
        return {day.date.isoformat(): day for day in result.days}

    def test_window_is_single_month(self):
        self._set_orders([])
        result = self.service.for_month(2026, 2)
        self.assertEqual(len(result.days), 28)
        self.assertEqual(result.days[0].date.isoformat(), "2026-02-01")
        self.assertEqual(result.days[-1].date.isoformat(), "2026-02-28")

    def test_window_year_wrap_for_december(self):
        self._set_orders([])
        result = self.service.for_month(2026, 12)
        end = result.days[-1].date
        self.assertEqual(end.isoformat(), "2026-12-31")
        self.assertEqual(result.end.isoformat(), "2026-12-31")

    def test_aggregates_min_avg_max_per_day(self):
        self._set_orders([
            order_on("2026-02-03", 100.0),
            order_on("2026-02-03", 300.0),
            order_on("2026-02-03", 200.0),
        ])
        result = self.service.for_month(2026, 2)
        day = self._days(result)["2026-02-03"]
        self.assertEqual(day.count, 3)
        self.assertAlmostEqual(day.min_ms, 100.0, places=2)
        self.assertAlmostEqual(day.max_ms, 300.0, places=2)
        self.assertAlmostEqual(day.avg_ms, 200.0, places=2)

    def test_order_without_executed_time_excluded(self):
        no_exec = order_on("2026-02-03", 100.0)
        no_exec.executed_time = None
        self._set_orders([no_exec, order_on("2026-02-03", 250.0)])
        result = self.service.for_month(2026, 2)
        day = self._days(result)["2026-02-03"]
        self.assertEqual(day.count, 1)
        self.assertAlmostEqual(day.avg_ms, 250.0, places=2)

    def test_zero_fills_empty_days(self):
        self._set_orders([order_on("2026-02-10", 150.0)])
        result = self.service.for_month(2026, 2)
        by_date = self._days(result)
        empty = by_date["2026-02-03"]
        self.assertEqual((empty.count, empty.min_ms, empty.max_ms, empty.avg_ms), (0, 0.0, 0.0, 0.0))
        filled = by_date["2026-02-10"]
        self.assertEqual(filled.count, 1)
        self.assertAlmostEqual(filled.min_ms, 150.0, places=2)

    def test_response_uses_half_open_query(self):
        self._set_orders([])
        self.service.for_month(2026, 2)
        start_dt, end_dt = self.repo.get_by_date_range.call_args[0]
        self.assertEqual(start_dt.isoformat(), "2026-02-01T00:00:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-03-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
