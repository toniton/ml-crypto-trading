from decimal import Decimal
from src.exchange.clients.ccxt.ccxt_mapper import CCXTTickerMapper


class TestCCXTTickerMapper:
    def test_bid_price_mapped_correctly(self):
        source = {
            "baseVolume": 100,
            "high": 51000,
            "low": 49000,
            "close": 50000,
            "bid": 49990.5,
            "ask": 50010.5,
            "timestamp": 1600000000000,
        }
        market_data = CCXTTickerMapper().map(source)
        assert market_data.bid_price == Decimal("49990.5")

    def test_ask_price_mapped_correctly(self):
        source = {
            "baseVolume": 100,
            "high": 51000,
            "low": 49000,
            "close": 50000,
            "bid": 49990.5,
            "ask": 50010.5,
            "timestamp": 1600000000000,
        }
        market_data = CCXTTickerMapper().map(source)
        assert market_data.ask_price == Decimal("50010.5")

    def test_bid_price_none_when_absent(self):
        source = {
            "baseVolume": 100,
            "high": 51000,
            "low": 49000,
            "close": 50000,
            "timestamp": 1600000000000,
        }
        market_data = CCXTTickerMapper().map(source)
        assert market_data.bid_price is None

    def test_ask_price_none_when_absent(self):
        source = {
            "baseVolume": 100,
            "high": 51000,
            "low": 49000,
            "close": 50000,
            "timestamp": 1600000000000,
        }
        market_data = CCXTTickerMapper().map(source)
        assert market_data.ask_price is None
