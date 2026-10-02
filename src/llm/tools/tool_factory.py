from __future__ import annotations

from typing import Dict, List, Optional

from langchain_core.tools import BaseTool

from api.interfaces.asset import Asset
from src.agent.backtest.backtest_service import BacktestService
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.oracle.oracle_service import OracleService
from src.agent.oracle.oracle_tool import AnalyzeTradingStateTool, GetTradingSummaryTool
from src.backtest.analysis.drift_detector import BacktestDriftDetector
from src.configuration.llm_config import LlmConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.trading_journal import TradingJournal
from src.metrics.services.metric_service import MetricService
from src.server.timeline_projector import TimelineProjector
from src.trading.managers.manager_container import ManagerContainer
from src.vcs.application.service import VCSService
from src.llm.tools.account_balance_tool import AccountBalanceTool
from src.llm.tools.backtest_drift_tool import BacktestDriftTool
from src.llm.tools.backtest_tool import BacktestTool
from src.llm.tools.configuration_history_tool import ConfigurationHistoryTool
from src.llm.tools.configuration_tool import ConfigurationTool
from src.llm.tools.consensus_tool import ConsensusTool
from src.llm.tools.exchange_fees_tool import ExchangeFeesTool
from src.llm.tools.exchange_read_tool import ExchangeReadOnlyTool
from src.llm.tools.market_statistics_tool import MarketStatisticsTool
from src.llm.tools.metrics_tool import MetricsTool
from src.llm.tools.open_orders_tool import GetOpenOrdersTool
from src.llm.tools.portfolio_summary_tool import PortfolioSummaryTool
from src.llm.tools.position_tool import PositionTool
from src.llm.tools.recent_trades_tool import RecentTradesTool
from src.llm.tools.session_summary_tool import SessionSummaryTool
from src.llm.tools.strategy_votes_tool import StrategyVotesTool
from src.llm.tools.trade_attribution_tool import TradeAttributionTool
from src.llm.tools.trading_context_tool import TradingContextTool


class ToolFactory:
    """Instantiates bot tools and filters enabled tools based on configuration."""

    @staticmethod
    def build_tool_map(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-boolean-expressions
            managers: Optional[ManagerContainer],
            assets: list[Asset],
            trading_journal: Optional[TradingJournal] = None,
            vcs: Optional[VCSService] = None,
            oracle_service: Optional[OracleService] = None,
            timeline_projector: Optional[TimelineProjector] = None,
            backtest_service: Optional[BacktestService] = None,
            metric_service: Optional[MetricService] = None,
            db_manager: Optional[DatabaseManager] = None,
    ) -> Dict[str, BaseTool]:
        configuration_service = ConfigurationService(vcs=vcs) if vcs else None
        drift_detector = (
            BacktestDriftDetector(backtest_service, trading_journal)
            if backtest_service and trading_journal
            else None
        )

        tools: Dict[str, BaseTool] = {}

        if managers.session_manager is not None:
            tools["trading_context"] = TradingContextTool(
                session_manager=managers.session_manager,
            )

        if managers.fees_manager is not None:
            tools["exchange_fees"] = ExchangeFeesTool(
                fees_manager=managers.fees_manager,
                assets=assets,
            )

        if managers.market_data_manager is not None:
            tools["market_statistics"] = MarketStatisticsTool(
                market_data_manager=managers.market_data_manager,
                assets=assets,
            )

        if managers.order_manager is not None:
            tools["open_orders"] = GetOpenOrdersTool(
                order_manager=managers.order_manager,
                assets=assets,
            )

        if managers.account_manager is not None:
            tools["account_balance"] = AccountBalanceTool(
                account_manager=managers.account_manager,
                assets=assets,
            )

        if managers.session_manager is not None:
            tools["position"] = PositionTool(
                session_manager=managers.session_manager,
                assets=assets,
            )

        if trading_journal is not None:
            tools["recent_trades"] = RecentTradesTool(
                trading_journal=trading_journal,
                assets=assets,
            )

        has_consensus_deps = (
                managers.consensus_manager is not None
                and managers.session_manager is not None
                and managers.market_data_manager is not None
        )
        if has_consensus_deps:
            tools["consensus"] = ConsensusTool(
                consensus_manager=managers.consensus_manager,
                session_manager=managers.session_manager,
                market_data_manager=managers.market_data_manager,
                assets=assets,
            )
            tools["strategy_votes"] = StrategyVotesTool(
                consensus_manager=managers.consensus_manager,
                session_manager=managers.session_manager,
                market_data_manager=managers.market_data_manager,
                assets=assets,
            )

        if configuration_service is not None:
            tools["configuration"] = ConfigurationTool(configuration_service=configuration_service)

        if vcs is not None:
            tools["configuration_history"] = ConfigurationHistoryTool(vcs=vcs)

        if managers.session_manager is not None:
            tools["session_summary"] = SessionSummaryTool(session_manager=managers.session_manager)

        if oracle_service is not None and timeline_projector is not None:
            tools["trading_summary"] = GetTradingSummaryTool(
                oracle_service=oracle_service,
                timeline_projector=timeline_projector,
            )

        if oracle_service is not None:
            tools["analyze_trading_state"] = AnalyzeTradingStateTool(oracle_service=oracle_service)

        if backtest_service is not None:
            tools["backtest"] = BacktestTool(backtest_service=backtest_service)

        if drift_detector is not None:
            tools["backtest_drift"] = BacktestDriftTool(drift_detector=drift_detector)

        if metric_service is not None:
            tools["metrics"] = MetricsTool(metric_service=metric_service)

        if db_manager is not None and managers.session_manager is not None:
            tools["trade_attribution"] = TradeAttributionTool(
                database_manager=db_manager,
                session_manager=managers.session_manager,
            )

        if managers.rest_manager is not None:
            tools["exchange_read"] = ExchangeReadOnlyTool(rest_manager=managers.rest_manager)

        if managers.portfolio_risk_manager is not None:
            tools["portfolio_summary"] = PortfolioSummaryTool(
                portfolio_risk_manager=managers.portfolio_risk_manager
            )

        return tools

    @staticmethod
    def get_enabled_tools(
            tool_map: Dict[str, BaseTool],
            llm_config: LlmConfig,
    ) -> List[BaseTool]:
        enabled_tools: List[BaseTool] = []
        for name, tool in tool_map.items():
            if llm_config.is_tool_enabled(name):
                enabled_tools.append(tool)
        return enabled_tools
