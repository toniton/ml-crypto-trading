import unittest
from unittest.mock import MagicMock, patch

from src.configuration.application_config import ApplicationConfig


class TestApplicationHeadless(unittest.TestCase):
    def setUp(self):
        self.argv_patcher = patch("sys.argv", ["pytest"])
        self.argv_patcher.start()
        self.addCleanup(self.argv_patcher.stop)

    def test_application_config_headless_default(self):
        config = ApplicationConfig(trading_config_filepath="config.yaml")
        self.assertFalse(config.headless)

    def test_application_config_headless_explicit_true(self):
        config = ApplicationConfig(trading_config_filepath="config.yaml", headless=True)
        self.assertTrue(config.headless)

    @patch("src.application.Application._setup_configuration")
    @patch("src.application.DatabaseManager")
    @patch("src.application.VCSService")
    @patch("src.application.RefChangeListener")
    @patch("src.application.ClientFactory")
    @patch("src.application.ModelFactory")
    @patch("src.application.TradingEngine")
    @patch("src.application.ApiServer")
    def test_application_starts_api_server_when_not_headless(
            self, mock_api_server_cls, mock_trading_engine, mock_model_factory,
            mock_client_factory, mock_ref_listener, mock_vcs, mock_db_manager, mock_setup_config
    ):
        from src.application import Application
        from src.configuration.environment_config import EnvironmentConfig
        from src.configuration.llm_config import LlmConfig
        from src.configuration.trading_config import TradingConfig

        app_config = ApplicationConfig(trading_config_filepath="config.yaml", headless=False)
        env_config = MagicMock(spec=EnvironmentConfig)
        trading_config = MagicMock(spec=TradingConfig)
        trading_config.assets = []
        trading_config.consensus = MagicMock()
        trading_config.dynamic_quantity = None
        llm_config = LlmConfig()

        mock_server_instance = MagicMock()
        mock_api_server_cls.return_value = mock_server_instance

        app = Application(app_config, env_config, trading_config, llm_config)
        app.startup()

        mock_api_server_cls.assert_called_once()
        mock_server_instance.start.assert_called_once()

        app.shutdown()
        mock_server_instance.stop.assert_called_once()

    @patch("src.application.Application._setup_configuration")
    @patch("src.application.DatabaseManager")
    @patch("src.application.VCSService")
    @patch("src.application.RefChangeListener")
    @patch("src.application.ClientFactory")
    @patch("src.application.ModelFactory")
    @patch("src.application.TradingEngine")
    @patch("src.application.ApiServer")
    def test_application_skips_api_server_when_headless(
            self, mock_api_server_cls, mock_trading_engine, mock_model_factory,
            mock_client_factory, mock_ref_listener, mock_vcs, mock_db_manager, mock_setup_config
    ):
        from src.application import Application
        from src.configuration.environment_config import EnvironmentConfig
        from src.configuration.llm_config import LlmConfig
        from src.configuration.trading_config import TradingConfig

        app_config = ApplicationConfig(trading_config_filepath="config.yaml", headless=True)
        env_config = MagicMock(spec=EnvironmentConfig)
        trading_config = MagicMock(spec=TradingConfig)
        trading_config.assets = []
        trading_config.consensus = MagicMock()
        trading_config.dynamic_quantity = None
        llm_config = LlmConfig()

        app = Application(app_config, env_config, trading_config, llm_config)
        app.startup()

        mock_api_server_cls.assert_not_called()

        app.shutdown()


if __name__ == "__main__":
    unittest.main()
