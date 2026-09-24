from __future__ import annotations

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.recorder.market_data_store import MarketDataStore
from src.trading.events import MarketDataEvent


class MarketDataRecorder:
    MARKET_DATA_EVENT_TYPES = (MarketDataEvent.__name__,)

    def __init__(self, store: MarketDataStore) -> None:
        self._store = store
        self._subscription_ids: list[str] = []

    def subscribe(self, event_bus: EventBus) -> list[str]:
        for event_type in MarketDataRecorder.MARKET_DATA_EVENT_TYPES:
            subscription_id = event_bus.subscribe(
                event_type, CallbackSubscription(self.on_market_data)
            )
            self._subscription_ids.append(subscription_id)
        return self._subscription_ids

    def on_market_data(self, event: Event) -> None:
        if isinstance(event, MarketDataEvent):
            self._store.record(event.ticker_symbol, event.market_data)
