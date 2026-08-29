from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel

from api.interfaces.order import Order
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository


class LatencyDay(BaseModel):
    date: date
    count: int
    avg_ms: float
    min_ms: float
    max_ms: float


class OrderLatencyResponse(BaseModel):
    year: int
    month: int
    start: date
    end: date
    days: list[LatencyDay]


class OrderLatencyService:
    def __init__(self, database_manager: DatabaseManager) -> None:
        self._database_manager = database_manager

    def for_month(self, year: int, month: int) -> OrderLatencyResponse:
        start = date(year, month, 1)
        end = self._last_day(year, month)
        orders = self._fetch_orders(start, end)

        day_map = {
            d: {"count": 0, "total_ms": 0.0, "min_ms": None, "max_ms": None}
            for d in self._days(start, end)
        }

        for order in orders:
            if order.executed_time is None:
                continue
            order_date = datetime.fromtimestamp(order.created_time, tz=timezone.utc).date()
            counts = day_map.get(order_date)
            if counts is None:
                continue
            latency_ms = (order.executed_time - order.created_time) * 1000
            counts["count"] += 1
            counts["total_ms"] += latency_ms
            counts["min_ms"] = (
                latency_ms if counts["min_ms"] is None else min(counts["min_ms"], latency_ms)
            )
            counts["max_ms"] = (
                latency_ms if counts["max_ms"] is None else max(counts["max_ms"], latency_ms)
            )

        days = [
            LatencyDay(
                date=d,
                count=c["count"],
                avg_ms=c["total_ms"] / c["count"] if c["count"] else 0.0,
                min_ms=c["min_ms"] or 0.0,
                max_ms=c["max_ms"] or 0.0,
            )
            for d, c in day_map.items()
        ]
        return OrderLatencyResponse(year=year, month=month, start=start, end=end, days=days)

    def _fetch_orders(self, start: date, end: date) -> list[Order]:
        start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresOrderRepository)
            return repository.get_by_date_range(start_dt, end_dt)

    @staticmethod
    def _last_day(year: int, month: int) -> date:
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)

    @staticmethod
    def _days(start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days
