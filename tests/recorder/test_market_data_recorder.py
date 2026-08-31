from decimal import Decimal

from api.interfaces.market_data import MarketData
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_recorder import MarketDataRecorder
from src.recorder.market_data_store import MarketDataStore
from src.trading.events import MarketDataEvent


class TestMarketDataRecorder:
    def test_records_market_data_event(self):
        store = MarketDataStore()
        recorder = MarketDataRecorder(store)
        bus = MessageEventBus()
        recorder.subscribe(bus)

        bus.publish(MarketDataEvent(
            ticker_symbol="BTC_USD",
            market_data=MarketData(
                close_price=Decimal("100"),
                high_price=Decimal("110"),
                low_price=Decimal("90"),
                volume=Decimal("1000"),
                timestamp=1700000000.0,
            ),
        ))

        observations = store.observations("BTC_USD")
        assert len(observations) == 1
        assert observations[0].close_price == Decimal("100")
        assert observations[0].high_price == Decimal("110")
        assert observations[0].low_price == Decimal("90")
        assert observations[0].volume == Decimal("1000")
