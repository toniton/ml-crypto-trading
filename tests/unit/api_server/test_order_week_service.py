import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.database.database_manager import DatabaseManager
from src.server.services.order_week_service import OrderWeekService


def order_on(day_iso: str, action: TradeAction):
    dt = datetime.fromisoformat(day_iso).replace(tzinfo=timezone.utc)
    return Order(
        uuid=f"u-{day_iso}-{action.value}",
        provider_name="p1",
        ticker_symbol="BTC",
        price=Decimal("42500.50"),
        quantity="0.00005",
        trade_action=action,
        created_time=dt.timestamp(),
    )


class TestOrderWeekService(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock(spec=DatabaseManager)
        self.uow = MagicMock()
        self.db_manager.get_unit_of_work.return_value = self.uow
        self.uow.__enter__.return_value = self.uow
        self.repo = self.uow.get_repository.return_value
        self.service = OrderWeekService(self.db_manager)

    def test_week_window_and_counts(self):
        # 2026-08-08 is a Saturday; the week is Mon 2026-08-03 .. Sun 2026-08-09.
        self.repo.get_by_date_range.return_value = [
            order_on("2026-08-03", TradeAction.BUY),
            order_on("2026-08-03", TradeAction.SELL),
            order_on("2026-08-08", TradeAction.BUY),
        ]
        result = self.service.for_week(2026, 8, 8)
        self.assertEqual(result.start, date(2026, 8, 3))
        self.assertEqual(result.end, date(2026, 8, 9))
        self.assertEqual(len(result.days), 7)
        by_date = {d.date: d.count for d in result.days}
        self.assertEqual(by_date[date(2026, 8, 3)], 2)
        self.assertEqual(by_date[date(2026, 8, 8)], 1)
        self.assertEqual(by_date[date(2026, 8, 5)], 0)

    def test_uses_half_open_week_range(self):
        self.repo.get_by_date_range.return_value = []
        self.service.for_week(2026, 8, 8)
        start, end = self.repo.get_by_date_range.call_args[0]
        self.assertEqual(start, datetime(2026, 8, 3, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 10, tzinfo=timezone.utc))

    def test_empty_week(self):
        self.repo.get_by_date_range.return_value = []
        result = self.service.for_week(2026, 8, 8)
        self.assertEqual(len(result.days), 7)
        self.assertTrue(all(day.count == 0 for day in result.days))


if __name__ == "__main__":
    unittest.main()
