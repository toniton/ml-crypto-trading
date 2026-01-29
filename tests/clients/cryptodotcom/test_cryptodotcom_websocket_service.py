import unittest
from unittest.mock import MagicMock, patch

from src.clients.cryptodotcom.cryptodotcom_websocket_builder import CryptoDotComWebSocketBuilder
from src.clients.cryptodotcom.cryptodotcom_websocket_service import CryptoDotComWebSocketService
from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.subscription_data import SubscriptionVisibility


class TestCryptoDotComWebSocketService(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock(spec=ExchangesConfig)
        self.config.crypto_dot_com = MagicMock()
        self.config.crypto_dot_com.websocket_endpoint = "wss://stream.crypto.com"

        # Patching ExchangesConfig class in the service module
        patcher = patch('src.clients.cryptodotcom.cryptodotcom_websocket_service.ExchangesConfig',
                        return_value=self.config)
        self.mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = CryptoDotComWebSocketService()

    def test_get_provider_name(self):
        self.assertEqual(self.service.get_provider_name(), "CRYPTO_DOT_COM")

    def test_get_websocket_url_public(self):
        url = self.service.get_websocket_url(SubscriptionVisibility.PUBLIC)
        self.assertEqual(url, "wss://stream.crypto.commarket")

    def test_get_websocket_url_private(self):
        url = self.service.get_websocket_url(SubscriptionVisibility.PRIVATE)
        self.assertEqual(url, "wss://stream.crypto.comuser")

    def test_create_builder(self):
        builder = self.service.builder()
        self.assertIsInstance(builder, CryptoDotComWebSocketBuilder)

    @patch('src.clients.cryptodotcom.cryptodotcom_websocket_service.WebSocketApp')
    @patch('threading.Thread')
    def test_ensure_connection_signaling(self, mock_thread, mock_ws_app):
        # Setup - mock the wait to avoid blocking
        with patch('threading.Event.wait', return_value=True):
            self.service.connect(MagicMock())

        # Verify connection event was created
        exchange = self.service.get_provider_name()
        conn_id = f"{exchange}-{SubscriptionVisibility.PUBLIC.value}"
        self.assertIn(conn_id, self.service._connection_events)

        # Simulate on_open to set the event
        self.service._handle_open(exchange, SubscriptionVisibility.PUBLIC)
        self.assertTrue(self.service._connection_events[conn_id].is_set())

    @patch('src.clients.cryptodotcom.cryptodotcom_websocket_service.WebSocketApp')
    @patch('threading.Thread')
    def test_inject_message_dispatch(self, mock_thread, mock_ws_app):
        with patch('threading.Event.wait', return_value=True):
            callback = MagicMock()
            self.service.connect(callback)

        exchange = self.service.get_provider_name()
        test_data = {"id": 1, "method": "subscribe", "result": {"data": "test"}}

        # Inject message (assuming it's not a heartbeat or auth response)
        self.service.inject_message(exchange, SubscriptionVisibility.PUBLIC, test_data)

        callback.assert_called_once_with(exchange, SubscriptionVisibility.PUBLIC, test_data)

    @patch('src.clients.cryptodotcom.cryptodotcom_websocket_service.WebSocketApp')
    @patch('threading.Thread')
    def test_inject_message_heartbeat(self, mock_thread, mock_ws_app):
        with patch('threading.Event.wait', return_value=True):
            callback = MagicMock()
            self.service.connect(callback)

        exchange = self.service.get_provider_name()
        heartbeat_data = {"method": "public/heartbeat"}

        with patch.object(self.service, 'get_heartbeat_handler') as mock_handler:
            mock_inst = MagicMock()
            mock_handler.return_value = mock_inst
            mock_inst.is_heartbeat.return_value = True
            mock_inst.get_heartbeat_response.return_value = {"method": "public/respond-heartbeat"}

            # Setup a connection to send heartbeat response
            mock_conn = MagicMock()
            self.service._connections[exchange] = {SubscriptionVisibility.PUBLIC: mock_conn}

            self.service.inject_message(exchange, SubscriptionVisibility.PUBLIC, heartbeat_data)

            # Should NOT call the main callback
            callback.assert_not_called()
            # Should send respond-heartbeat
            mock_conn.send.assert_called_once()

    @patch('src.clients.cryptodotcom.cryptodotcom_websocket_service.WebSocketApp')
    @patch('threading.Thread')
    def test_subscribe_waits_for_connection(self, mock_thread, mock_ws_app):
        mock_builder = MagicMock(spec=CryptoDotComWebSocketBuilder)
        mock_builder.get_subscription_data.return_value = MagicMock(
            payload={'method': 'subscribe'},
            visibility=SubscriptionVisibility.PUBLIC
        )

        exchange = self.service.get_provider_name()
        conn_id = f"{exchange}-{SubscriptionVisibility.PUBLIC.value}"

        # Setup connection in state
        mock_conn = MagicMock()
        self.service._connections[exchange] = {SubscriptionVisibility.PUBLIC: mock_conn}

        # Mock event and wait
        mock_event = MagicMock()
        self.service._connection_events[conn_id] = mock_event

        # Execute
        self.service.subscribe(mock_builder)

        # Verify it waited and then sent
        mock_event.wait.assert_called_once()
        mock_conn.send.assert_called_once()
