from decimal import Decimal

import pytest

from api.interfaces.market_data import MarketData
from src.backtest.backtest_event_bus import BacktestEventBus, BacktestCallbackSubscription
from src.backtest.events.domain_events import BacktestEvent, TickEvent
from src.trading.events import MarketDataEvent


class _NotAnEvent:
    pass


def _market_data() -> MarketData:
    return MarketData(
        close_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        volume=Decimal("1000"),
        timestamp=1.0,
    )


class TestBacktestEventBus:
    def test_publish_accepts_backtest_event(self):
        bus = BacktestEventBus()
        received = []
        bus.subscribe_callback(TickEvent, received.append)

        bus.publish(TickEvent(tick_time=1))

        assert len(received) == 1
        assert isinstance(received[0], BacktestEvent)

    def test_publish_accepts_shared_market_data_event(self):
        bus = BacktestEventBus()
        received = []
        bus.subscribe_callback(MarketDataEvent, received.append)

        bus.publish(MarketDataEvent(ticker_symbol="BTC_USD", market_data=_market_data()))

        assert len(received) == 1
        assert received[0].ticker_symbol == "BTC_USD"

    def test_subscribe_callback_rejects_non_event_class(self):
        bus = BacktestEventBus()

        with pytest.raises(TypeError):
            bus.subscribe_callback(_NotAnEvent, lambda e: None)

    def test_callback_subscription_accepts_event(self):
        received = []
        subscription = BacktestCallbackSubscription(received.append)

        subscription.put(TickEvent(tick_time=1))

        assert len(received) == 1
        assert isinstance(received[0], BacktestEvent)
