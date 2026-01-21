import unittest
from unittest.mock import MagicMock, patch

from src.clients.cryptodotcom.cryptodotcom_rest_service import CryptoDotComRestService
from src.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder
from src.configuration.exchanges_config import ExchangesConfig


class TestCryptoDotComRestService(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock(spec=ExchangesConfig)
        self.config.crypto_dot_com = MagicMock()
        self.config.crypto_dot_com.rest_endpoint = "https://api.crypto.com"
        self.config.crypto_dot_com.api_key = "test_key"
        self.config.crypto_dot_com.secret_key = "test_secret"

        # Patching ExchangesConfig class in the service module
        patcher = patch('src.clients.cryptodotcom.cryptodotcom_rest_service.ExchangesConfig', return_value=self.config)
        self.mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = CryptoDotComRestService()

    def test_get_provider_name(self):
        self.assertEqual(self.service.get_provider_name(), "CRYPTO_DOT_COM")

    def test_create_builder(self):
        builder = self.service.builder()
        self.assertIsInstance(builder, CryptoDotComRestBuilder)

    @patch('src.trading.helpers.request_helper.RequestHelper.execute_request')
    def test_execute_generic(self, mock_execute):
        mock_execute.return_value = {"result": "success"}
        builder = MagicMock(spec=CryptoDotComRestBuilder)

        # Mocking generic Mapper
        mock_mapper = MagicMock()
        mock_mapper.map.return_value = {"mapped": "result"}
        builder.mapper.return_value = mock_mapper

        builder.build_request.return_value = MagicMock()

        result = self.service.execute(builder)

        self.assertEqual(result, {"mapped": "result"})
        builder.build_request.assert_called_with("https://api.crypto.com")
        builder.sign.assert_called_with("test_key", "test_secret")
        mock_execute.assert_called_once()
        mock_mapper.map.assert_called_once()
