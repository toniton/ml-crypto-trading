from api.interfaces.timeframe import Timeframe
from src.exchange.clients.ccxt.ccxt_rest_builder import CCXTExchangeRestBuilder
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder


class TestCandleRangeBuilders:
    def test_ccxt_builder_sets_since_and_limit_in_ms(self):
        builder = CCXTExchangeRestBuilder("CCXT_BINANCE").candles(
            "BTC/USDT",
            Timeframe.MIN5,
            start_time=1700000000.0,
            limit=300,
        )
        endpoint = builder.get_endpoint()

        assert endpoint.params["since"] == 1700000000000
        assert endpoint.params["limit"] == 300

    def test_cryptodotcom_builder_sets_start_ts_end_ts_and_count(self):
        builder = CryptoDotComRestBuilder().candles(
            "BTC_USD",
            Timeframe.MIN5,
            start_time=1700000000.0,
            end_time=1700003600.0,
            limit=300,
        )
        params = builder.get_params()

        assert params["instrument_name"] == "BTC_USD"
        assert params["start_ts"] == 1700000000000
        assert params["end_ts"] == 1700003600000
        assert params["count"] == 300
