from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order, OrderStatus
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_websocket_service import BacktestWebSocketService
from backtest.events.domain_events import (
    BalanceUpdateEvent,
    MarketDataEvent,
    OrderFillEvent,
)
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum


class TestBacktestWebSocketService:
    @pytest.fixture
    def event_bus(self):
        return BacktestEventBus()

    @pytest.fixture
    def assets(self):
        return [
            Asset(
                base_ticker_symbol="BTC",
                quote_ticker_symbol="USD",
                decimal_places=8,
                name="Bitcoin",
                exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
                min_quantity=0.001,
                schedule=AssetSchedule.EVERY_MINUTE,
                candles_timeframe=Timeframe.MIN1
            ),
            Asset(
                base_ticker_symbol="ETH",
                quote_ticker_symbol="USD",
                decimal_places=8,
                name="Ethereum",
                exchange=ExchangeProvidersEnum.CCXT_BINANCE,
                min_quantity=0.01,
                schedule=AssetSchedule.EVERY_MINUTE,
                candles_timeframe=Timeframe.MIN1
            ),
        ]

    @pytest.fixture
    def service(self, event_bus):
        return BacktestWebSocketService(event_bus=event_bus)

    def test_market_data_dispatch(self, service, event_bus):
        callback = MagicMock()
        service.connect(callback)

        market_data = MarketData(
            close_price=Decimal("50000"),
            low_price=Decimal("49000"),
            high_price=Decimal("51000"),
            volume=Decimal("10"),
            timestamp=1234567890.0
        )
        event = MarketDataEvent(ticker_symbol="BTC_USD", market_data=market_data)
        event_bus.publish(event)

        callback.assert_called_once_with(
            ExchangeProvidersEnum.BACKTEST.value,
            SubscriptionVisibility.PUBLIC,
            {
                "type": "market_data",
                "ticker_symbol": "BTC_USD",
                "data": market_data
            }
        )

    def test_order_fill_dispatch(self, service, event_bus):
        callback = MagicMock()
        service.connect(callback)

        order = Order(
            uuid="123",
            ticker_symbol="BTC_USD",
            quantity="0.1",
            price=Decimal("50000"),
            status=OrderStatus.COMPLETED,
            provider_name=ExchangeProvidersEnum.CRYPTO_DOT_COM.value,
            trade_action=TradeAction.BUY,
            created_time=1234567890.0
        )
        event = OrderFillEvent(order=order)
        event_bus.publish(event)

        callback.assert_called_once_with(
            ExchangeProvidersEnum.BACKTEST.value,
            SubscriptionVisibility.PRIVATE,
            {
                "type": "order_update",
                "instrument_name": "BTC_USD",
                "data": [order]
            }
        )

    def test_balance_update_dispatch(self, service, event_bus):
        callback = MagicMock()
        service.connect(callback)

        balances = []  # Mock list of balances
        event = BalanceUpdateEvent(balances=balances)
        event_bus.publish(event)

        callback.assert_called_once_with(
            ExchangeProvidersEnum.BACKTEST.value,
            SubscriptionVisibility.PRIVATE,
            {
                "type": "balance",
                "data": balances
            }
        )
