from decimal import Decimal
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.agent.runtime_debug.error_extractor import ErrorExtractor
from src.agent.runtime_debug.models import ErrorSeverity
from src.trading.helpers.request_helper import ExchangeRequestError


def test_extract_runtime_error_standard_exception():
    exc = ValueError("Invalid execution price")
    order = Order(
        uuid="ord_1",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.1",
        trade_action=TradeAction.BUY,
        created_time=100.0,
    )

    event = ErrorExtractor.extract_runtime_error_from_order_exception(exc, order=order)

    assert event.error_type == "ValueError"
    assert event.message == "Invalid execution price"
    assert event.asset == "BTC_USD"
    assert event.order_id == "ord_1"
    assert event.exchange == "simulated"
    assert event.severity == ErrorSeverity.ERROR


def test_extract_runtime_error_exchange_request_error():
    cause = ExchangeRequestError(
        message="HTTP 400 Bad Request",
        http_status=400,
        response_body={"code": 10001, "message": "insufficient balance"},
        url="https://api.crypto.com/v2/order",
        method="POST",
    )
    exc = RuntimeError("Execution failed")
    exc.__cause__ = cause

    event = ErrorExtractor.extract_runtime_error_from_order_exception(exc)

    assert event.error_type == "RuntimeError"
    assert event.message == "insufficient balance"
    assert event.exchange_code == 10001
    assert event.http_status == 400
    assert event.severity == ErrorSeverity.CRITICAL
    assert event.metadata["url"] == "https://api.crypto.com/v2/order"
    assert event.metadata["method"] == "POST"
