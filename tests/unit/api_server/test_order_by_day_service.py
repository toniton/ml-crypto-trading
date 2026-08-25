import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.database_manager import DatabaseManager
from src.server.services.order_by_day_service import OrderByDayService


def order_on(day_iso: str, action: TradeAction, status=OrderStatus.COMPLETED, hour=10):
    dt = datetime.fromisoformat(day_iso).replace(hour=hour, tzinfo=timezone.utc)
    return Order(
        uuid=f"u-{day_iso}-{action.value}",
        provider_name="p1",
        ticker_symbol="BTC",
        price=Decimal("42500.50"),
        quantity="0.00005",
        trade_action=action,
        created_time=dt.timestamp(),
        status=status,
    )


class TestOrderByDayService(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock(spec=DatabaseManager)
        self.uow = MagicMock()
        self.db_manager.get_unit_of_work.return_value = self.uow
        self.uow.__enter__.return_value = self.uow
        self.repo = self.uow.get_repository.return_value
        self.service = OrderByDayService(self.db_manager)

    def test_returns_orders_for_day_sorted_by_time(self):
        self.repo.get_by_date_range.return_value = [
            order_on("2026-08-08", TradeAction.SELL, hour=14),
            order_on("2026-08-08", TradeAction.BUY, hour=9),
        ]
        result = self.service.for_date(2026, 8, 8)
        self.assertEqual(result.date, date(2026, 8, 8))
        self.assertEqual(result.count, 2)
        self.assertEqual([o.trade_action for o in result.orders], ["BUY", "SELL"])
        self.assertEqual(result.orders[0].price, "42500.50")
        self.assertEqual(result.orders[0].status, "COMPLETED")

    def test_uses_half_open_day_range(self):
        self.repo.get_by_date_range.return_value = []
        self.service.for_date(2026, 8, 8)
        start, end = self.repo.get_by_date_range.call_args[0]
        self.assertEqual(start, datetime(2026, 8, 8, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 9, tzinfo=timezone.utc))

    def test_no_orders_for_day(self):
        self.repo.get_by_date_range.return_value = []
        result = self.service.for_date(2026, 8, 8)
        self.assertEqual(result.count, 0)
        self.assertEqual(result.orders, [])


if __name__ == "__main__":
    unittest.main()
