import pytest

from src.backtest.backtest_event_bus import BacktestEventBus, BacktestCallbackSubscription
from src.backtest.events.domain_events import BacktestEvent, TickEvent


class _NotAnEvent:
    pass


class TestBacktestEventBusValidation:
    def test_publish_rejects_non_backtest_event(self):
        bus = BacktestEventBus()

        with pytest.raises(TypeError):
            bus.publish(_NotAnEvent())

    def test_publish_accepts_backtest_event(self):
        bus = BacktestEventBus()
        received = []
        bus.subscribe_callback(TickEvent, received.append)

        bus.publish(TickEvent(tick_time=1))

        assert len(received) == 1

    def test_subscribe_callback_rejects_non_backtest_class(self):
        bus = BacktestEventBus()

        with pytest.raises(TypeError):
            bus.subscribe_callback(_NotAnEvent, lambda e: None)

    def test_callback_subscription_rejects_non_backtest_event(self):
        subscription = BacktestCallbackSubscription(lambda e: None)

        with pytest.raises(TypeError):
            subscription.put(_NotAnEvent())

    def test_callback_subscription_accepts_backtest_event(self):
        received = []
        subscription = BacktestCallbackSubscription(received.append)

        subscription.put(TickEvent(tick_time=1))

        assert len(received) == 1
        assert isinstance(received[0], BacktestEvent)
