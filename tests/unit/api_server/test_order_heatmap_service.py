import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.database.database_manager import DatabaseManager
from src.server.services.order_heatmap_service import OrderHeatmapService


def order_on(day: str, action: TradeAction) -> Order:
    dt = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return Order(
        uuid=str(hash((day, action.value))),
        provider_name="p1",
        ticker_symbol="BTC",
        price="100",
        quantity="1",
        trade_action=action,
        created_time=dt.timestamp(),
    )


class TestOrderHeatmapService(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock(spec=DatabaseManager)
        self.uow = MagicMock()
        self.db_manager.get_unit_of_work.return_value = self.uow
        self.uow.__enter__.return_value = self.uow
        self.repo = self.uow.get_repository.return_value
        self.service = OrderHeatmapService(self.db_manager)

    def _set_orders(self, orders):
        self.repo.get_by_date_range.return_value = orders

    def test_window_three_full_months(self):
        self._set_orders([])
        result = self.service.daily_counts(2026, 10)
        self.assertEqual(result.start, date(2026, 8, 1))
        self.assertEqual(result.end, date(2026, 10, 31))
        self.assertEqual(len(result.days), 92)
        self.assertEqual(result.days[0].date, date(2026, 8, 1))
        self.assertEqual(result.days[-1].date, date(2026, 10, 31))

    def test_window_year_wrap_for_january(self):
        self._set_orders([])
        result = self.service.daily_counts(2026, 1)
        self.assertEqual(result.start, date(2025, 11, 1))
        self.assertEqual(result.end, date(2026, 1, 31))

    def test_buckets_buy_and_sell_per_day(self):
        self._set_orders([
            order_on("2026-10-01", TradeAction.BUY),
            order_on("2026-10-01", TradeAction.BUY),
            order_on("2026-10-01", TradeAction.SELL),
            order_on("2026-10-02", TradeAction.SELL),
        ])
        result = self.service.daily_counts(2026, 10)
        by_date = {day.date: day for day in result.days}
        day1 = by_date[date(2026, 10, 1)]
        self.assertEqual((day1.buy, day1.sell, day1.total), (2, 1, 3))
        day2 = by_date[date(2026, 10, 2)]
        self.assertEqual((day2.buy, day2.sell, day2.total), (0, 1, 1))

    def test_zero_fills_gaps(self):
        self._set_orders([order_on("2026-10-15", TradeAction.BUY)])
        result = self.service.daily_counts(2026, 10)
        by_date = {day.date: day for day in result.days}
        self.assertEqual(by_date[date(2026, 10, 3)].total, 0)
        self.assertEqual(by_date[date(2026, 10, 15)].total, 1)

    def test_orders_outside_window_ignored(self):
        self._set_orders([
            order_on("2026-07-31", TradeAction.BUY),
            order_on("2026-11-01", TradeAction.SELL),
        ])
        result = self.service.daily_counts(2026, 10)
        self.assertEqual(result.days[0].total, 0)
        self.assertEqual(result.days[-1].total, 0)

    def test_response_uses_half_open_query(self):
        self._set_orders([])
        self.service.daily_counts(2026, 10)
        start_dt, end_dt = self.repo.get_by_date_range.call_args[0]
        self.assertEqual(start_dt, datetime(2026, 8, 1, tzinfo=timezone.utc))
        self.assertEqual(end_dt, datetime(2026, 11, 1, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
