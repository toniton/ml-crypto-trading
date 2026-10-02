import unittest
from unittest.mock import MagicMock, patch

from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.llm_config import LlmConfig
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.llm.tools.backtest_tool import BacktestTool
from src.llm.tools.metrics_tool import MetricsTool
from src.vcs.application.service import VCSService


class TestBacktestToolWiring(unittest.TestCase):
    def setUp(self):
        self.argv_patcher = patch("sys.argv", ["pytest"])
        self.argv_patcher.start()
        self.addCleanup(self.argv_patcher.stop)

    @patch("src.application.Application._setup_clients")
    @patch("src.application.Application._setup_configuration")
    @patch("src.application.SqlAlchemyDatabaseManager")
    @patch("src.application.VCSService")
    @patch("src.application.RefChangeListener")
    @patch("src.trading.managers.manager_factory.ClientFactory")
    @patch("src.llm.llm_runtime_manager.ModelFactory")
    @patch("src.application.TradingEngine")
    @patch("src.application.ApiServer")
    def test_backtest_tool_is_bound_to_agent(
            self, mock_api_server_cls, mock_trading_engine, mock_model_factory,
            mock_client_factory, mock_ref_listener, mock_vcs, mock_db_manager,
            mock_setup_config, _mock_setup_clients,
    ):
        mock_vcs.return_value = MagicMock(spec=VCSService)
        mock_db_manager.return_value = MagicMock(spec=DatabaseManager)
        mock_client_factory.create_rest_manager.return_value = MagicMock(spec=ExchangeRestManager)

        api_llm = MagicMock()
        mock_model_factory.create_model.return_value = api_llm

        app_config = ApplicationConfig(trading_config_filepath="config.yaml", headless=False)
        env_config = MagicMock(spec=EnvironmentConfig)
        trading_config = MagicMock(spec=TradingConfig)
        trading_config.assets = []
        trading_config.consensus = MagicMock()
        trading_config.dynamic_quantity = None
        llm_config = LlmConfig()

        app = Application(app_config, env_config, trading_config, llm_config)
        app.startup()

        self.assertTrue(api_llm.bind_tools.called)
        bound_tools = api_llm.bind_tools.call_args[0][0]
        self.assertTrue(
            any(isinstance(tool, BacktestTool) for tool in bound_tools),
            "BacktestTool is not bound to the agent LLM",
        )
        self.assertTrue(
            any(isinstance(tool, MetricsTool) for tool in bound_tools),
            "MetricsTool is not bound to the agent LLM",
        )

        app.shutdown()

