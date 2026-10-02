from decimal import Decimal
from src.exchange.clients.cryptodotcom.mappers.cryptodotcom_mappers import (
    CryptoDotComAccountBalanceMapper,
    CryptoDotComMarketDataMapper,
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


class TestCryptoDotComMarketDataMapper:
    def _sample_ticker_payload(self, **overrides):
        data = {
            "h": "65000.0",
            "l": "63000.0",
            "a": "64000.0",
            "i": "BTC_USD",
            "v": "120.5",
            "vv": "7712000.0",
            "b": "63990.0",
            "k": "64010.0",
            "t": 1700000000000,
        }
        data.update(overrides)
        return {
            "id": 1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "channel": "ticker.BTC_USD",
                "subscription": "ticker.BTC_USD",
                "data": [data],
            },
        }

    def test_bid_price_mapped_correctly(self):
        market_data = CryptoDotComMarketDataMapper().map(self._sample_ticker_payload())
        assert market_data.bid_price == Decimal("63990.0")

    def test_ask_price_mapped_correctly(self):
        market_data = CryptoDotComMarketDataMapper().map(self._sample_ticker_payload())
        assert market_data.ask_price == Decimal("64010.0")

    def test_bid_price_none_when_missing(self):
        market_data = CryptoDotComMarketDataMapper().map(self._sample_ticker_payload(b=None))
        assert market_data.bid_price is None

    def test_ask_price_none_when_missing(self):
        market_data = CryptoDotComMarketDataMapper().map(self._sample_ticker_payload(k=None))
        assert market_data.ask_price is None


class TestCryptoDotComAccountBalanceMapper:
    def test_user_balance_official_spec_payload_mapping(self):
        payload = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "subscription": "user.balance",
                "channel": "user.balance",
                "data": [
                    {
                        "instrument_name": "USD",
                        "total_available_balance": "58.90813519",
                        "total_margin_balance": "58.90813519",
                        "total_initial_margin": "0.0",
                        "total_maintenance_margin": "0.0",
                        "total_position_cost": "0.0",
                        "total_cash_balance": "58.90813519",
                        "total_collateral_value": "58.90813519",
                        "total_session_unrealized_pnl": "0.0",
                        "total_session_realized_pnl": "0.0",
                        "is_liquidating": False,
                        "total_effective_leverage": "0.0",
                        "position_limit": "1000000.0",
                        "used_position_limit": "0.0",
                        "total_isolated_cash_balance": "0.0",
                        "total_position_im": "0.0",
                        "total_haircut": "0.0",
                        "position_balances": [
                            {
                                "instrument_name": "USD",
                                "quantity": "58.90813519",
                                "market_value": "58.90813519",
                                "collateral_eligible": True,
                                "haircut": "0",
                                "collateral_amount": "58.90813519",
                                "max_withdrawal_balance": "58.90813519",
                                "reserved_qty": "0",
                            },
                            {
                                "instrument_name": "BTC",
                                "quantity": "0.00004",
                                "market_value": "2.60",
                                "collateral_eligible": True,
                                "haircut": "0.1",
                                "collateral_amount": "2.34",
                                "max_withdrawal_balance": "0.00004",
                                "reserved_qty": "0",
                            },
                        ],
                    }
                ],
            },
        }

        mapper = CryptoDotComAccountBalanceMapper()
        balances = mapper.map(payload)

        assert len(balances) == 2
        usd = next(b for b in balances if b.currency == "USD")
        btc = next(b for b in balances if b.currency == "BTC")

        assert usd.available_balance == Decimal("58.90813519")
        assert btc.available_balance == Decimal("0.00004")

