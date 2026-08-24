from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository


class HeatmapDay(BaseModel):
    date: date
    buy: int
    sell: int
    total: int


class OrderHeatmapResponse(BaseModel):
    year: int
    month: int
    start: date
    end: date
    days: list[HeatmapDay]


class OrderHeatmapService:
    def __init__(self, database_manager: DatabaseManager) -> None:
        self._database_manager = database_manager

    def daily_counts(self, year: int, month: int) -> OrderHeatmapResponse:
        start = self._first_day(year, month, -2)
        end = self._first_day(year, month, 1) - timedelta(days=1)
        orders = self._fetch_orders(start, self._first_day(year, month, 1))

        day_map = {d: {"buy": 0, "sell": 0, "total": 0} for d in self._days(start, end)}

        for order in orders:
            order_date = datetime.fromtimestamp(order.created_time, tz=timezone.utc).date()
            counts = day_map.get(order_date)
            if counts is None:
                continue
            counts["total"] += 1
            if order.trade_action == TradeAction.BUY:
                counts["buy"] += 1
            elif order.trade_action == TradeAction.SELL:
                counts["sell"] += 1

        days = [
            HeatmapDay(date=d, buy=c["buy"], sell=c["sell"], total=c["total"])
            for d, c in day_map.items()
        ]
        return OrderHeatmapResponse(year=year, month=month, start=start, end=end, days=days)

    def _fetch_orders(self, start: date, end: date) -> list[Order]:
        start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresOrderRepository)
            return repository.get_by_date_range(start_dt, end_dt)

    @staticmethod
    def _first_day(year: int, month: int, delta: int) -> date:
        total = year * 12 + (month - 1) + delta
        return date(total // 12, total % 12 + 1, 1)

    @staticmethod
    def _days(start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days
