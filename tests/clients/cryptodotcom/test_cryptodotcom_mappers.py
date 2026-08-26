from src.exchange.clients.cryptodotcom.mappers.cryptodotcom_mappers import (
    CryptoDotComOrderMapper,
    CryptoDotComOrdersMapper,
)

UPDATE_TIME_MS = 1767738403882


def _filled_order_result(**overrides):
    result = {
        "account_id": "acct",
        "client_oid": "uuid-1",
        "side": "BUY",
        "status": "FILLED",
        "instrument_name": "BTC_USD",
        "quantity": "1",
        "limit_price": "50000",
        "create_time_ns": "1767738400000000000",
        "update_time": UPDATE_TIME_MS,
    }
    result.update(overrides)
    return result


class TestCryptoDotComOrderMapper:
    def test_executed_time_converts_ms_to_seconds(self):
        order = CryptoDotComOrderMapper().map({
            "id": 1,
            "method": "private/get-order-detail",
            "code": 0,
            "result": _filled_order_result(),
        })
        assert order.executed_time == UPDATE_TIME_MS / 1000

    def test_executed_time_none_when_not_completed(self):
        order = CryptoDotComOrderMapper().map({
            "id": 1,
            "method": "private/get-order-detail",
            "code": 0,
            "result": _filled_order_result(status="ACTIVE"),
        })
        assert order.executed_time is None

    def test_executed_time_none_when_missing_update_time(self):
        order = CryptoDotComOrderMapper().map({
            "id": 1,
            "method": "private/get-order-detail",
            "code": 0,
            "result": _filled_order_result(update_time=None),
        })
        assert order.executed_time is None


class TestCryptoDotComOrdersMapper:
    def test_executed_time_converts_ms_to_seconds(self):
        orders = CryptoDotComOrdersMapper().map({
            "id": 1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "channel": "user.order",
                "subscription": "x",
                "data": [_filled_order_result()],
            },
        })
        assert orders[0].executed_time == UPDATE_TIME_MS / 1000
