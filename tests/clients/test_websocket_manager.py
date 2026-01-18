import unittest
from unittest.mock import MagicMock, patch
from src.clients.websocket_manager import WebSocketManager
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class TestWebSocketManager(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('src.core.logging.application_logging_mixin.ApplicationLoggingMixin.app_logger')
        self.mock_logger = self.patcher.start()
        self.websocket_manager = WebSocketManager()

    def tearDown(self):
        self.patcher.stop()

    def test_register_service(self):
        mock_service = MagicMock()
        mock_service.get_provider_name.return_value = "BINANCE"
        self.websocket_manager.register_service(mock_service)

        self.assertIn("BINANCE", self.websocket_manager._connections)
        self.assertIn("BINANCE", self.websocket_manager._subscriptions)

    def test_connect_lazy(self):
        mock_service = MagicMock()
        mock_service.get_provider_name.return_value = "BINANCE"
        mock_service.get_websocket_url.return_value = "ws://test.com"
        self.websocket_manager.register_service(mock_service)

    @patch('src.clients.websocket_manager.WebSocketApp')
    @patch('threading.Thread')
    def test_ensure_connection(self, mock_thread, mock_ws_app):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "TEST_EXCHANGE"
        mock_service.get_websocket_url.return_value = "ws://test.url"
        
        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_service.create_builder.return_value = mock_builder

        self.websocket_manager.register_service(mock_service)
        self.websocket_manager._ensure_connection(mock_service, SubscriptionVisibility.PUBLIC)

        self.assertIn(SubscriptionVisibility.PUBLIC, self.websocket_manager._connections["TEST_EXCHANGE"])
        mock_ws_app.assert_called_once()
        mock_thread.assert_called_once()

    @patch('src.clients.websocket_manager.WebSocketApp')
    @patch('threading.Thread')
    def test_subscribe_market_data(self, _mock_thread, mock_ws_app):
        mock_service = MagicMock(spec=ExchangeWebSocketService)
        mock_service.get_provider_name.return_value = "TEST_EXCHANGE"
        mock_service.get_websocket_url.return_value = "ws://test.url"
        
        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_service.create_builder.return_value = mock_builder
        mock_builder.market_data.return_value = mock_builder

        sub_data = SubscriptionData(
            payload={"op": "sub"},
            visibility=SubscriptionVisibility.PUBLIC
        )
        mock_builder.get_subscription_data.return_value = sub_data

        mock_ws_inst = MagicMock()
        mock_ws_app.return_value = mock_ws_inst

        self.websocket_manager.register_service(mock_service)
        callback = MagicMock()

        self.websocket_manager.subscribe_market_data("TEST_EXCHANGE", "BTC_USDT", callback)

        mock_ws_inst.send.assert_called_with('{"op": "sub"}')
        
    def test_unsubscribe(self):
        mock_service = MagicMock()
        mock_service.get_provider_name.return_value = "BINANCE"
        self.websocket_manager.register_service(mock_service)
        
        # Mocking connections and subscriptions
        self.websocket_manager._connections["BINANCE"] = {SubscriptionVisibility.PUBLIC: MagicMock()}
        # Simulate subscription
        self.websocket_manager._subscriptions["BINANCE"] = {"MARKET_BTC-USD": (MagicMock(), MagicMock())}

        self.websocket_manager.unsubscribe_market_data("BINANCE", "BTC-USD")

        self.assertNotIn("MARKET_BTC-USD", self.websocket_manager._subscriptions["BINANCE"])
