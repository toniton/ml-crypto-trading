import unittest
from unittest.mock import MagicMock, patch

from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.exchange.managers.websocket_manager import WebSocketManager


class TestWebSocketManager(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('src.logging.application_logging_mixin.ApplicationLoggingMixin.app_logger')
        self.mock_logger = self.patcher.start()
        self.websocket_manager = WebSocketManager()

    def tearDown(self):
        self.patcher.stop()

    def test_register_service(self):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "BINANCE"
        self.websocket_manager.register_service(mock_service)

        self.assertIn("BINANCE", self.websocket_manager._subscriptions)

    def test_connect(self):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "BINANCE"
        self.websocket_manager.register_service(mock_service)

        self.websocket_manager.connect()

        mock_service.connect.assert_called_once_with(self.websocket_manager._handle_incoming_message)

    def test_subscribe_market_data(self):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "TEST_EXCHANGE"

        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_service.builder.return_value = mock_builder
        mock_builder.market_data.return_value = mock_builder

        self.websocket_manager.register_service(mock_service)
        callback = MagicMock()

        self.websocket_manager.subscribe_market_data("TEST_EXCHANGE", "BTC_USDT", callback)

        mock_service.subscribe.assert_called_once_with(mock_builder)
        self.assertEqual(self.websocket_manager._subscriptions["TEST_EXCHANGE"]["MARKET_BTC_USDT"],
                         (mock_builder, callback))

    def test_handle_incoming_message_dispatch(self):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "TEST_EXCHANGE"

        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)

        # Setup subscription data for matching
        sub_data = SubscriptionData(
            payload={"type": "ticker"},
            visibility=SubscriptionVisibility.PUBLIC,
            parser=lambda x: x["data"],
            filter=lambda x: x.get("type") == "ticker"
        )
        mock_builder.get_subscription_data.return_value = sub_data

        self.websocket_manager.register_service(mock_service)
        callback = MagicMock()

        # Manually inject subscription
        self.websocket_manager._subscriptions["TEST_EXCHANGE"]["key1"] = (mock_builder, callback)

        # Test matching message
        test_data = {"type": "ticker", "data": "val1"}
        self.websocket_manager._handle_incoming_message("TEST_EXCHANGE", SubscriptionVisibility.PUBLIC, test_data)

        callback.assert_called_once_with("val1")

    def test_handle_incoming_message_no_match(self):
        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        sub_data = SubscriptionData(
            payload={},
            visibility=SubscriptionVisibility.PRIVATE,
            filter=lambda x: False
        )
        mock_builder.get_subscription_data.return_value = sub_data

        self.websocket_manager._subscriptions["TEST"] = {"key1": (mock_builder, MagicMock())}

        callback = self.websocket_manager._subscriptions["TEST"]["key1"][1]

        # Private visibility vs Public message
        self.websocket_manager._handle_incoming_message("TEST", SubscriptionVisibility.PUBLIC, {})
        callback.assert_not_called()

        # Filter returning False
        self.websocket_manager._handle_incoming_message("TEST", SubscriptionVisibility.PRIVATE, {})
        callback.assert_not_called()

    def test_unsubscribe(self):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "BINANCE"
        self.websocket_manager.register_service(mock_service)

        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        callback = MagicMock()
        self.websocket_manager._subscriptions["BINANCE"]["MARKET_BTC-USD"] = (mock_builder, callback)

        self.websocket_manager.unsubscribe_market_data("BINANCE", "BTC-USD")

        mock_service.unsubscribe.assert_called_once_with(mock_builder)
        self.assertNotIn("MARKET_BTC-USD", self.websocket_manager._subscriptions["BINANCE"])
