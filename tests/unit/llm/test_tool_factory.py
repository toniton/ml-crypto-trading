import unittest
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from src.agent.backtest.backtest_service import BacktestService
from src.agent.oracle.oracle_service import OracleService
from src.configuration.llm_config import LlmConfig, ToolConfig, ToolRegistryConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.trading_journal import TradingJournal
from src.exchange.managers.rest_manager import RestManager
from src.llm.tools.tool_factory import ToolFactory
from src.metrics.services.metric_service import MetricService
from src.server.timeline_projector import TimelineProjector
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.decision.decision_manager import DecisionManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.health.health_monitor import HealthMonitor
from src.trading.managers.manager_container import ManagerContainer
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager
from src.trading.session.session_manager import SessionManager
from src.vcs.application.service import VCSService


class TestToolFactory(unittest.TestCase):
    def _create_mock_managers(self) -> ManagerContainer:
        managers = MagicMock(spec=ManagerContainer)
        managers.fees_manager = MagicMock(spec=FeesManager)
        managers.market_data_manager = MagicMock(spec=MarketDataManager)
        managers.order_manager = MagicMock(spec=OrderManager)
        managers.account_manager = MagicMock(spec=AccountManager)
        managers.session_manager = MagicMock(spec=SessionManager)
        managers.consensus_manager = MagicMock(spec=ConsensusManager)
        managers.rest_manager = MagicMock(spec=RestManager)
        managers.portfolio_risk_manager = MagicMock(spec=PortfolioRiskManager)
        managers.decision_manager = MagicMock(spec=DecisionManager)
        managers.health_monitor = MagicMock(spec=HealthMonitor)
        return managers

    def test_build_core_trading_tools(self):
        managers = self._create_mock_managers()
        mock_asset = MagicMock(spec=Asset)
        trading_journal = MagicMock(spec=TradingJournal)

        core_tools = ToolFactory.build_core_trading_tools(
            managers=managers,
            assets=[mock_asset],
            trading_journal=trading_journal,
        )

        expected_tools = [
            "trading_context",
            "exchange_fees",
            "market_statistics",
            "open_orders",
            "account_balance",
            "position",
            "session_summary",
            "consensus",
            "strategy_votes",
            "inspect_trading_decision",
            "exchange_read",
            "portfolio_summary",
            "trading_health",
            "recent_trades",
        ]
        for name in expected_tools:
            self.assertIn(name, core_tools)

    def test_build_vcs_tools(self):
        vcs = MagicMock(spec=VCSService)
        tools = ToolFactory.build_vcs_tools(vcs=vcs)
        self.assertIn("configuration", tools)
        self.assertIn("configuration_history", tools)

    def test_build_backtest_tools(self):
        backtest_service = MagicMock(spec=BacktestService)
        trading_journal = MagicMock(spec=TradingJournal)
        tools = ToolFactory.build_backtest_tools(backtest_service, trading_journal)
        self.assertIn("backtest", tools)
        self.assertIn("backtest_drift", tools)

    def test_build_metric_tools(self):
        metric_service = MagicMock(spec=MetricService)
        tools = ToolFactory.build_metric_tools(metric_service)
        self.assertIn("metrics", tools)

    def test_build_attribution_tools(self):
        db_manager = MagicMock(spec=DatabaseManager)
        session_manager = MagicMock(spec=SessionManager)
        tools = ToolFactory.build_attribution_tools(db_manager, session_manager)
        self.assertIn("trade_attribution", tools)

    def test_build_oracle_tools(self):
        oracle_service = MagicMock(spec=OracleService)
        timeline_projector = MagicMock(spec=TimelineProjector)
        tools = ToolFactory.build_oracle_tools(oracle_service, timeline_projector)
        self.assertIn("trading_summary", tools)
        self.assertIn("analyze_trading_state", tools)

    def test_build_tool_map_and_filtering(self):
        managers = self._create_mock_managers()
        mock_asset = MagicMock(spec=Asset)

        tool_map = ToolFactory.build_tool_map(
            managers=managers,
            assets=[mock_asset],
            trading_journal=MagicMock(spec=TradingJournal),
            vcs=MagicMock(spec=VCSService),
            oracle_service=MagicMock(spec=OracleService),
            timeline_projector=MagicMock(spec=TimelineProjector),
            backtest_service=MagicMock(spec=BacktestService),
            metric_service=MagicMock(spec=MetricService),
            db_manager=MagicMock(spec=DatabaseManager),
        )

        self.assertIn("trading_context", tool_map)
        self.assertIn("exchange_fees", tool_map)
        self.assertIn("market_statistics", tool_map)
        self.assertIn("open_orders", tool_map)
        self.assertIn("account_balance", tool_map)
        self.assertIn("position", tool_map)
        self.assertIn("recent_trades", tool_map)
        self.assertIn("consensus", tool_map)
        self.assertIn("strategy_votes", tool_map)
        self.assertIn("configuration", tool_map)
        self.assertIn("configuration_history", tool_map)
        self.assertIn("session_summary", tool_map)
        self.assertIn("trading_summary", tool_map)
        self.assertIn("analyze_trading_state", tool_map)
        self.assertIn("backtest", tool_map)
        self.assertIn("backtest_drift", tool_map)
        self.assertIn("metrics", tool_map)
        self.assertIn("trade_attribution", tool_map)
        self.assertIn("inspect_trading_decision", tool_map)
        self.assertIn("exchange_read", tool_map)
        self.assertIn("portfolio_summary", tool_map)
        self.assertIn("trading_health", tool_map)

        # Test filtering disabled tools
        config = LlmConfig.model_construct(
            tools=ToolRegistryConfig(
                bot_tools=[
                    ToolConfig(name="trading_context", enabled=True),
                    ToolConfig(name="exchange_fees", enabled=False),
                ]
            )
        )
        enabled_tools = ToolFactory.get_enabled_tools(
            {"trading_context": tool_map["trading_context"], "exchange_fees": tool_map["exchange_fees"]},
            config,
        )
        self.assertEqual(len(enabled_tools), 1)


if __name__ == "__main__":
    unittest.main()
