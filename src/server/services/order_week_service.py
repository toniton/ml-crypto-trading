from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from pydantic import BaseModel

from api.interfaces.order import Order
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository


class OrderWeekDay(BaseModel):
    date: date
    count: int


class OrderWeekResponse(BaseModel):
    start: date
    end: date
    days: list[OrderWeekDay]


class OrderWeekService:
    def __init__(self, database_manager: DatabaseManager) -> None:
        self._database_manager = database_manager

    def for_week(self, year: int, month: int, day: int) -> OrderWeekResponse:
        target = date(year, month, day)
        monday = target - timedelta(days=target.weekday())
        sunday = monday + timedelta(days=6)
        orders = self._fetch_orders(monday, sunday)
        counts = {d: 0 for d in self._days(monday, sunday)}
        for order in orders:
            order_date = datetime.fromtimestamp(order.created_time, tz=timezone.utc).date()
            if order_date in counts:
                counts[order_date] += 1
        days = [OrderWeekDay(date=d, count=counts[d]) for d in self._days(monday, sunday)]
        return OrderWeekResponse(start=monday, end=sunday, days=days)

    def _fetch_orders(self, monday: date, sunday: date) -> list[Order]:
        start = datetime.combine(monday, time.min, tzinfo=timezone.utc)
        end = datetime.combine(sunday + timedelta(days=1), time.min, tzinfo=timezone.utc)
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresOrderRepository)
            return repository.get_by_date_range(start, end)

    @staticmethod
    def _days(start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days
