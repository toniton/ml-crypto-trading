from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from api.interfaces.order import Order
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository


class OrderDetail(BaseModel):
    uuid: str
    ticker_symbol: str
    provider_name: str
    trade_action: str
    order_type: str
    price: str
    quantity: str
    status: str
    created_time: float
    latency_ms: Optional[float] = None
    fees: Optional[float] = None
    slippage: Optional[float] = None


class OrderByDayResponse(BaseModel):
    date: date
    count: int
    orders: list[OrderDetail]


class OrderByDayService:
    def __init__(self, database_manager: DatabaseManager) -> None:
        self._database_manager = database_manager

    def for_date(self, year: int, month: int, day: int) -> OrderByDayResponse:
        target = date(year, month, day)
        orders = self._fetch_orders(target)
        details = [self._to_detail(order) for order in orders]
        details.sort(key=lambda order: order.created_time)
        return OrderByDayResponse(date=target, count=len(details), orders=details)

    def _fetch_orders(self, target: date) -> list[Order]:
        start = datetime.combine(target, time.min, tzinfo=timezone.utc)
        end = datetime.combine(target + timedelta(days=1), time.min, tzinfo=timezone.utc)
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresOrderRepository)
            return repository.get_by_date_range(start, end)

    @staticmethod
    def _to_detail(order: Order) -> OrderDetail:
        latency_ms = None
        if order.executed_time is not None:
            latency_ms = (order.executed_time - order.created_time) * 1000
        slippage = None
        if order.fill_price is not None and order.price and order.price != 0:
            slippage = float((order.fill_price - order.price) / order.price * 100)
        return OrderDetail(
            uuid=order.uuid,
            ticker_symbol=order.ticker_symbol,
            provider_name=order.provider_name,
            trade_action=order.trade_action.value if hasattr(order.trade_action, "value") else order.trade_action,
            order_type="LIMIT",
            price=str(order.price),
            quantity=order.quantity,
            status=order.status.value if hasattr(order.status, "value") else order.status,
            created_time=order.created_time,
            latency_ms=latency_ms,
            fees=float(order.fees) if order.fees is not None else None,
            slippage=slippage,
        )
