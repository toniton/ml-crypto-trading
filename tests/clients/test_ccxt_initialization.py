import unittest
from unittest.mock import MagicMock, patch

from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import AppEnvEnum, EnvironmentConfig
from src.configuration.llm_config import LlmConfig
from src.exchange.clients.ccxt.ccxt_rest_service import CCXTExchangeRestService
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


class TestCCXTInitialization(unittest.TestCase):
    def setUp(self):
        self.app_config = MagicMock(spec=ApplicationConfig)
        self.app_config.simulated = False
        self.app_config.trading_config_filepath = None

        self.env_config = EnvironmentConfig(
            app_env=AppEnvEnum.STAGING,
            database_connection_host="localhost"
        )

        self.trading_config = MagicMock()
        self.trading_config.assets = []
        self.trading_config.dynamic_quantity = None

    @patch('src.application.DatabaseManager')
    def test_application_initializes_all_ccxt_providers(self, mock_db):
        # We need to ensure the modules are imported so subclasses are known

        with patch('src.exchange.clients.ccxt.ccxt_rest_service.CCXTExchangeRestService.__init__',
                   autospec=True) as mock_rest_init, \
                patch('src.exchange.clients.ccxt.ccxt_websocket_service.CCXTExchangeWebSocketService.__init__',
                      autospec=True) as mock_ws_init:

            def rest_side_effect(self, provider):
                self._provider = provider

            mock_rest_init.side_effect = rest_side_effect

            def ws_side_effect(self, provider):
                self._provider = provider

            mock_ws_init.side_effect = ws_side_effect

            app = Application(
                application_config=self.app_config,
                environment_config=self.env_config,
                trading_config=self.trading_config,
                llm_config=LlmConfig()
            )

        # Supported providers: 'binance', 'kraken', 'coinbase', 'bybit', 'kucoin' (5) + 'cryptodotcom' (1)
        ccxt_providers = CCXTExchangeRestService.get_supported_providers()
        self.assertEqual(len(ccxt_providers), 5)

        # Verify REST services registered
        for provider in list(ccxt_providers) + [ExchangeProvidersEnum.CRYPTO_DOT_COM]:
            provider_name = provider.value if isinstance(provider, ExchangeProvidersEnum) else provider
            self.assertTrue(app._managers.rest_manager.get_service(provider_name) is not None)

        # Verify WebSocket services registered
        for provider in list(ccxt_providers) + [ExchangeProvidersEnum.CRYPTO_DOT_COM]:
            provider_name = provider.value if isinstance(provider, ExchangeProvidersEnum) else provider
            self.assertTrue(app._managers.websocket_manager.get_service(provider_name) is not None)

        self.assertEqual(mock_rest_init.call_count, 5)
        self.assertEqual(mock_ws_init.call_count, 5)
