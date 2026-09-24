from __future__ import annotations

import traceback
from typing import Any, Optional

from api.interfaces.order import Order
from src.agent.runtime_debug.models import ErrorSeverity, RuntimeErrorEvent
from src.trading.helpers.request_helper import ExchangeRequestError


def extract_runtime_error_from_order_exception(
        exc: Exception,
        order: Optional[Order] = None,
        component: str = "trading.orders.order_manager",
        operation: str = "execute_order",
) -> RuntimeErrorEvent:
    http_status: Optional[int] = None
    exchange_code: Optional[int] = None
    message = str(exc)
    metadata: dict[str, Any] = {}

    current: Optional[BaseException] = exc
    while current is not None:
        if isinstance(current, ExchangeRequestError):
            http_status = current.http_status
            if isinstance(current.response_body, dict):
                exchange_code = current.response_body.get("code")
                msg = current.response_body.get("message")
                if msg:
                    message = msg
                metadata["exchange_response"] = current.response_body
            elif isinstance(current.response_body, str):
                metadata["raw_response"] = current.response_body
            if current.url:
                metadata["url"] = current.url
            if current.method:
                metadata["method"] = current.method
            break
        current = current.__cause__ or current.__context__

    if order is not None:
        metadata["order_quantity"] = str(order.quantity)
        metadata["order_price"] = str(order.price)
        metadata["trade_action"] = order.trade_action.value

    severity = ErrorSeverity.ERROR
    if http_status == 400 and exchange_code:
        severity = ErrorSeverity.CRITICAL

    return RuntimeErrorEvent(
        severity=severity,
        component=component,
        error_type=type(exc).__name__,
        message=message,
        traceback=traceback.format_exc(),
        operation=operation,
        asset=order.ticker_symbol if order else None,
        order_id=order.uuid if order else None,
        exchange=order.provider_name if order else None,
        exchange_code=exchange_code,
        http_status=http_status,
        commit_hash=order.commit_hash if order else None,
        metadata=metadata,
    )
