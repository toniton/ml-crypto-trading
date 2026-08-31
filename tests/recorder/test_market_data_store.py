from decimal import Decimal

from api.interfaces.market_data import MarketData
from src.recorder.market_data_store import MarketDataStore


def _market_data(timestamp: int, close: str) -> MarketData:
    return MarketData(
        close_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        volume=Decimal("100"),
        timestamp=float(timestamp),
    )


class TestMarketDataStore:
    def test_records_and_returns_sorted_observations(self):
        store = MarketDataStore()
        store.record("BTC_USD", _market_data(200, "101"))
        store.record("BTC_USD", _market_data(100, "100"))

        assert store.tickers() == ("BTC_USD",)
        assert [int(observation.timestamp) for observation in store.observations("BTC_USD")] == [100, 200]

    def test_latest_observation_wins_per_timestamp(self):
        store = MarketDataStore()
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(100, "101"))

        observations = store.observations("BTC_USD")
        assert len(observations) == 1
        assert observations[0].close_price == Decimal("101")

    def test_evicts_oldest_beyond_cap(self):
        store = MarketDataStore(max_observations=3)
        for timestamp in range(1, 6):
            store.record("BTC_USD", _market_data(timestamp, str(timestamp)))

        observations = store.observations("BTC_USD")
        assert [int(observation.timestamp) for observation in observations] == [3, 4, 5]

    def test_empty_store(self):
        store = MarketDataStore()

        assert not store.tickers()
        assert not store.observations("BTC_USD")

    def test_dataset_id(self):
        store = MarketDataStore()

        assert store.dataset_id("BTC_USD") == "recorded:BTC_USD"
