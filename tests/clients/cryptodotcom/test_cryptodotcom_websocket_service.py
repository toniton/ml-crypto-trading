import unittest
from unittest.mock import MagicMock, patch

from src.clients.cryptodotcom.cryptodotcom_websocket_service import CryptoDotComWebSocketService
from src.clients.cryptodotcom.cryptodotcom_websocket_builder import CryptoDotComWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.configuration.exchanges_config import ExchangesConfig


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
        builder = self.service.create_builder()
        self.assertIsInstance(builder, CryptoDotComWebSocketBuilder)

    def test_get_auth_request(self):
        # Assuming CryptoDotComAuthHandler is working (it's tested separately ideally)
        # But here we just check if it returns a dict.
        with patch(
                'src.clients.cryptodotcom.handlers.auths.cryptodotcom_auth_handler.CryptoDotComAuthHandler.get_auth_request') as mock_auth:
            mock_auth.return_value = {"method": "auth"}
            req = self.service.get_auth_request()
            self.assertEqual(req, {"method": "auth"})
