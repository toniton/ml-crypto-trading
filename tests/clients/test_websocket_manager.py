import unittest
from unittest.mock import MagicMock, patch
from src.clients.websocket_manager import WebSocketManager
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class TestWebSocketManager(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('src.core.logging.application_logging_mixin.ApplicationLoggingMixin.app_logger')
        self.mock_logger = self.patcher.start()
        self.manager = WebSocketManager()

    def tearDown(self):
        self.patcher.stop()

    def test_register_websocket(self):
        mock_client = MagicMock(spec=ExchangeWebSocketClient)
        mock_client.get_provider_name.return_value = "TEST_EXCHANGE"

        self.manager.register_websocket(mock_client)

        self.assertIn("TEST_EXCHANGE", self.manager.websockets)
        self.assertIn("TEST_EXCHANGE", self.manager._connections)
        self.assertIn("TEST_EXCHANGE", self.manager._subscriptions)

    @patch('src.clients.websocket_manager.WebSocketApp')
    @patch('threading.Thread')
    def test_ensure_connection(self, mock_thread, mock_ws_app):
        mock_client = MagicMock(spec=ExchangeWebSocketClient)
        mock_client.get_provider_name.return_value = "TEST_EXCHANGE"
        mock_client.get_websocket_url.return_value = "ws://test.url"

        self.manager.register_websocket(mock_client)
        self.manager._ensure_connection(mock_client, SubscriptionVisibility.PUBLIC)

        self.assertIn(SubscriptionVisibility.PUBLIC, self.manager._connections["TEST_EXCHANGE"])
        mock_ws_app.assert_called_once()
        mock_thread.assert_called_once()

    @patch('src.clients.websocket_manager.WebSocketApp')
    @patch('threading.Thread')
    def test_subscribe_market_data(self, _mock_thread, mock_ws_app):
        mock_client = MagicMock(spec=ExchangeWebSocketClient)
        mock_client.get_provider_name.return_value = "TEST_EXCHANGE"
        mock_client.get_websocket_url.return_value = "ws://test.url"
        mock_client.market_data.return_value = mock_client

        sub_data = SubscriptionData(
            payload={"op": "sub"},
            visibility=SubscriptionVisibility.PUBLIC
        )
        mock_client.get_subscription_data.return_value = sub_data

        mock_ws_inst = MagicMock()
        mock_ws_app.return_value = mock_ws_inst

        self.manager.register_websocket(mock_client)
        callback = MagicMock()

        self.manager.subscribe_market_data("TEST_EXCHANGE", "BTC_USDT", callback)

        self.assertIn("MARKET_BTC_USDT", self.manager._subscriptions["TEST_EXCHANGE"])
        mock_ws_inst.send.assert_called_with('{"op": "sub"}')

    @patch('src.clients.websocket_manager.WebSocketApp')
    @patch('threading.Thread')
    def test_unsubscribe(self, _mock_thread, _mock_ws_app):
        mock_client = MagicMock(spec=ExchangeWebSocketClient)
        mock_client.get_provider_name.return_value = "TEST_EXCHANGE"
        mock_client.get_unsubscribe_payload.return_value = {"op": "unsub"}

        sub_data = SubscriptionData(
            payload={"op": "sub"},
            visibility=SubscriptionVisibility.PUBLIC
        )

        mock_ws_inst = MagicMock()
        self.manager.register_websocket(mock_client)
        self.manager._connections["TEST_EXCHANGE"][SubscriptionVisibility.PUBLIC] = mock_ws_inst
        self.manager._subscriptions["TEST_EXCHANGE"]["TEST_KEY"] = (sub_data, MagicMock())

        self.manager._unsubscribe("TEST_EXCHANGE", "TEST_KEY")

        mock_ws_inst.send.assert_called_with('{"op": "unsub"}')
        self.assertNotIn("TEST_KEY", self.manager._subscriptions["TEST_EXCHANGE"])
