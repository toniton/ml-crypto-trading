from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.agent.monitoring.activity_state import AssetActivityState
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


def _asset(schedule: Optional[AssetSchedule] = AssetSchedule.EVERY_MINUTE) -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=schedule,
        candles_timeframe=Timeframe.MIN1,
        enabled=True,
    )


class FakeProvider:
    def __init__(self, state: Optional[AssetActivityState], started_at: float):
        self._state = state
        self._started = started_at

    @property
    def started_at(self) -> float:
        return self._started

    def state_for(self, ticker_symbol: str) -> Optional[AssetActivityState]:
        return self._state

    def states(self) -> list:
        return [self._state] if self._state else []


def _capture(bus):
    captured = []

    def handler(event):
        captured.append(event)

    sid = bus.subscribe("TradingActivityAnomalyDetectedEvent", CallbackSubscription(handler))
    return captured, sid


def test_threshold_schedule_derived_with_fallback():
    bus = MessageEventBus()
    provider = FakeProvider(None, time.time() - 10000)
    watchdog = StarvationWatchdog(
        activity_provider=provider,
        assets=[_asset(AssetSchedule.EVERY_MINUTE)],
        event_bus=bus,
        missed_intervals_threshold=3.0,
        grace_period_seconds=60.0,
        fallback_threshold_seconds=86400.0,
    )
    assert watchdog._threshold_for(_asset(AssetSchedule.EVERY_MINUTE)) == 240.0

    # Fallback applies when the schedule is not a recognised cadence.
    fallback_asset = SimpleNamespace(schedule="UNKNOWN")
    assert watchdog._threshold_for(fallback_asset) == 86400.0 * 3 + 60.0


def test_no_trigger_when_recent_activity():
    bus = MessageEventBus()
    now = time.time()
    state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now,
        last_evaluation_at=now,
        last_signal_at=now,
        last_order_at=now,
        last_execution_at=now,
    )
    provider = FakeProvider(state, now - 10000)
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[_asset()], event_bus=bus
    )
    assert watchdog.run_once() == []


def test_trigger_emits_anomaly_event_once():
    bus = MessageEventBus()
    captured, _sid = _capture(bus)
    state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=time.time() - 10000,
    )
    provider = FakeProvider(state, time.time() - 10000)
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[_asset()], event_bus=bus
    )

    emitted = watchdog.run_once()
    assert len(emitted) == 1
    event = emitted[0]
    assert event.asset == "BTC_USD"
    assert event.anomaly_kind == "NO_MARKET_DATA"
    assert len(captured) == 1

    # Dedup: a second poll must not re-emit.
    assert watchdog.run_once() == []
    assert len(captured) == 1


def test_trigger_cleared_when_activity_resumes():
    bus = MessageEventBus()
    captured, _sid = _capture(bus)
    stale = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=time.time() - 10000,
    )
    provider = FakeProvider(stale, time.time() - 10000)
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[_asset()], event_bus=bus
    )
    assert len(watchdog.run_once()) == 1

    # Activity resumes -> triggered state cleared.
    provider._state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=time.time(),
    )
    assert watchdog.run_once() == []

    # Starvation returns -> re-detection is possible.
    provider._state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=time.time() - 10000,
    )
    assert len(watchdog.run_once()) == 1
    assert len(captured) == 2


def test_classify_downstream_anomaly_kind():
    bus = MessageEventBus()
    provider = FakeProvider(None, time.time() - 10000)
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[_asset()], event_bus=bus
    )
    now = time.time()

    # Market data + evaluations alive, but no signal -> strategy behaviour.
    state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now,
        last_evaluation_at=now,
        last_signal_at=now - 10000,
    )
    assert watchdog._classify(state, now, 240.0) == "NO_SIGNALS"

    # Market data + evaluations alive, but no signal ever emitted -> strategy behaviour.
    state_no_signal = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now,
        last_evaluation_at=now,
    )
    assert watchdog._classify(state_no_signal, now, 240.0, baseline=now - 300.0) == "NO_SIGNALS"

    # Signals alive, but no orders ever submitted -> risk/config gating problem.
    state_no_order = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now,
        last_evaluation_at=now,
        last_signal_at=now,
    )
    assert watchdog._classify(state_no_order, now, 240.0, baseline=now - 400.0) == "NO_ORDERS"

    # Everything alive except executions -> exchange/order problem.
    state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now,
        last_evaluation_at=now,
        last_signal_at=now,
        last_order_at=now,
        last_execution_at=now - 10000,
    )
    assert watchdog._classify(state, now, 240.0) == "NO_EXECUTIONS"


def test_start_stop_lifecycle():
    bus = MessageEventBus()
    provider = FakeProvider(None, time.time())
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[], event_bus=bus, poll_interval_seconds=0.05
    )
    watchdog.start()
    watchdog.stop()
    watchdog.start()
    watchdog.stop()