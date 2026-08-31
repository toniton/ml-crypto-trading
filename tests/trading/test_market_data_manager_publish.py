from decimal import Decimal
from unittest.mock import Mock, patch

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events import MarketDataEvent
from src.trading.markets.market_data_manager import MarketDataManager


def _asset() -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.0001,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
    )


def _market_data(timestamp: float, close: str) -> MarketData:
    return MarketData(
        close_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        volume=Decimal("1000"),
        timestamp=timestamp,
    )


class TestMarketDataManagerPublish:
    def test_publishes_market_data_event_on_new_tick(self):
        asset = _asset()
        bus = MessageEventBus()
        received = []
        bus.subscribe(MarketDataEvent.__name__, CallbackSubscription(received.append))

        manager = MarketDataManager(Mock(), Mock(), event_bus=bus)
        with patch.object(manager, "get_candles", return_value=[]):
            manager.initialize([asset])

        manager._update_market_data(asset.key, _market_data(1700000000.0, "100"))

        assert len(received) == 1
        assert received[0].ticker_symbol == "BTC_USD"
        assert received[0].market_data.close_price == Decimal("100")

    def test_does_not_publish_outdated_tick(self):
        asset = _asset()
        bus = MessageEventBus()
        received = []
        bus.subscribe(MarketDataEvent.__name__, CallbackSubscription(received.append))

        manager = MarketDataManager(Mock(), Mock(), event_bus=bus)
        with patch.object(manager, "get_candles", return_value=[]):
            manager.initialize([asset])

        manager._update_market_data(asset.key, _market_data(1700000000.0, "100"))
        manager._update_market_data(asset.key, _market_data(1699999000.0, "99"))

        assert len(received) == 1
        assert received[0].market_data.close_price == Decimal("100")
