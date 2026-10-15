from datetime import timedelta
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

    def test_default_retention_is_time_based(self):
        store = MarketDataStore()

        assert store.max_age == timedelta(hours=6)

    def test_prunes_observations_older_than_max_age_on_record(self):
        store = MarketDataStore(max_age=timedelta(seconds=100))
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(150, "150"))
        store.record("BTC_USD", _market_data(250, "250"))

        timestamps = [int(o.timestamp) for o in store.observations("BTC_USD")]
        assert timestamps == [150, 250]

    def test_prune_by_cutoff_returns_removed_count(self):
        store = MarketDataStore(max_age=None)
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(200, "200"))
        store.record("ETH_USD", _market_data(100, "10"))

        assert store.count_before(150) == 2
        removed = store.prune(150)

        assert removed == 2
        assert [int(o.timestamp) for o in store.observations("BTC_USD")] == [200]
        assert store.tickers() == ("BTC_USD",)

    def test_set_max_age_updates_retention(self):
        store = MarketDataStore(max_age=None)
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(500, "500"))

        store.set_max_age(timedelta(seconds=100))
        assert store.max_age == timedelta(seconds=100)

        assert store.prune(450) == 1
        assert store.size() == 1

    def test_dataset_id(self):
        store = MarketDataStore()

        assert store.dataset_id("BTC_USD") == "recorded:BTC_USD"
