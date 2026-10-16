from __future__ import annotations

from typing import Any, Dict, List, Optional

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
from src.llm.tools.account_balance_tool import AccountBalanceTool
from src.llm.tools.backtest_drift_tool import BacktestDriftTool
from src.llm.tools.backtest_tool import BacktestTool
from src.llm.tools.configuration_history_tool import ConfigurationHistoryTool
from src.llm.tools.configuration_tool import ConfigurationTool
from src.llm.tools.consensus_tool import ConsensusTool
from src.llm.tools.decision_inspector_tool import DecisionInspectorTool
from src.llm.tools.exchange_fees_tool import ExchangeFeesTool
from src.llm.tools.exchange_read_tool import ExchangeReadOnlyTool
from src.llm.tools.experiment_inspector_tool import ExperimentInspectorTool
from src.llm.tools.market_statistics_tool import MarketStatisticsTool
from src.llm.tools.metrics_tool import MetricsTool
from src.llm.tools.open_orders_tool import GetOpenOrdersTool
from src.llm.tools.portfolio_summary_tool import PortfolioSummaryTool
from src.llm.tools.position_tool import PositionTool
from src.llm.tools.recent_trades_tool import RecentTradesTool
from src.llm.tools.retention_governance_tool import RetentionGovernanceTool
from src.llm.tools.session_summary_tool import SessionSummaryTool
from src.llm.tools.strategy_optimizer_tool import StrategyOptimizerTool
from src.llm.tools.strategy_votes_tool import StrategyVotesTool
from src.llm.tools.tick_trace_tool import ScheduleTickTracer, TickTraceTool
from src.llm.tools.trade_attribution_tool import TradeAttributionTool
from src.llm.tools.trading_context_tool import TradingContextTool
from src.llm.tools.trading_health_tool import TradingHealthTool
from src.llm.tools.walk_forward_tool import WalkForwardTool
from src.metrics.services.metric_service import MetricService
from src.retention.manager import RetentionManager
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)
from src.server.services.walk_forward_application_service import (
    WalkForwardApplicationService,
)
from src.server.timeline_projector import TimelineProjector
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.managers.manager_container import ManagerContainer
from src.trading.session.session_manager import SessionManager
from src.vcs.application.service import VCSService


class ToolFactory:
    """Instantiates bot tools and filters enabled tools based on configuration."""

    @staticmethod
    def build_core_trading_tools(
            managers: ManagerContainer,
            assets: list[Asset],
            trading_journal: TradingJournal,
    ) -> Dict[str, BaseTool]:
        return {
            "trading_context": TradingContextTool(
                session_manager=managers.session_manager,
            ),
            "exchange_fees": ExchangeFeesTool(
                fees_manager=managers.fees_manager,
                assets=assets,
            ),
            "market_statistics": MarketStatisticsTool(
                market_data_manager=managers.market_data_manager,
                assets=assets,
            ),
            "open_orders": GetOpenOrdersTool(
                order_manager=managers.order_manager,
                assets=assets,
            ),
            "account_balance": AccountBalanceTool(
                account_manager=managers.account_manager,
                assets=assets,
            ),
            "position": PositionTool(
                session_manager=managers.session_manager,
                assets=assets,
            ),
            "session_summary": SessionSummaryTool(
                session_manager=managers.session_manager,
            ),
            "consensus": ConsensusTool(
                consensus_manager=managers.consensus_manager,
                session_manager=managers.session_manager,
                market_data_manager=managers.market_data_manager,
                assets=assets,
            ),
            "strategy_votes": StrategyVotesTool(
                consensus_manager=managers.consensus_manager,
                session_manager=managers.session_manager,
                market_data_manager=managers.market_data_manager,
                assets=assets,
            ),
            "inspect_trading_decision": DecisionInspectorTool(
                decision_manager=managers.decision_manager,
            ),
            "exchange_read": ExchangeReadOnlyTool(
                rest_manager=managers.rest_manager,
            ),
            "portfolio_summary": PortfolioSummaryTool(
                portfolio_risk_manager=managers.portfolio_risk_manager,
            ),
            "trading_health": TradingHealthTool(
                health_monitor=managers.health_monitor,
            ),
            "recent_trades": RecentTradesTool(
                trading_journal=trading_journal,
                assets=assets,
            ),
        }

    @staticmethod
    def build_vcs_tools(vcs: VCSService) -> Dict[str, BaseTool]:
        configuration_service = ConfigurationService(vcs=vcs)
        return {
            "configuration": ConfigurationTool(configuration_service=configuration_service),
            "configuration_history": ConfigurationHistoryTool(vcs=vcs),
        }

    @staticmethod
    def build_backtest_tools(
            backtest_service: BacktestService,
            trading_journal: Optional[TradingJournal] = None,
    ) -> Dict[str, BaseTool]:
        tools: Dict[str, BaseTool] = {
            "backtest": BacktestTool(backtest_service=backtest_service),
        }
        if trading_journal is not None:
            drift_detector = BacktestDriftDetector(backtest_service, trading_journal)
            tools["backtest_drift"] = BacktestDriftTool(drift_detector=drift_detector)
        return tools

    @staticmethod
    def build_metric_tools(metric_service: MetricService) -> Dict[str, BaseTool]:
        return {
            "metrics": MetricsTool(metric_service=metric_service),
        }

    @staticmethod
    def build_attribution_tools(
            db_manager: DatabaseManager,
            session_manager: SessionManager,
            configuration_service: Optional[ConfigurationService] = None,
    ) -> Dict[str, BaseTool]:
        tools: Dict[str, BaseTool] = {
            "trade_attribution": TradeAttributionTool(
                database_manager=db_manager,
                session_manager=session_manager,
            ),
        }
        if configuration_service is not None:
            tools["strategy_optimizer"] = StrategyOptimizerTool(
                database_manager=db_manager,
                configuration_service=configuration_service,
            )
        return tools

    @staticmethod
    def build_oracle_tools(
            oracle_service: OracleService,
            timeline_projector: Optional[TimelineProjector] = None,
    ) -> Dict[str, BaseTool]:
        tools: Dict[str, BaseTool] = {
            "analyze_trading_state": AnalyzeTradingStateTool(oracle_service=oracle_service),
        }
        if timeline_projector is not None:
            tools["trading_summary"] = GetTradingSummaryTool(
                oracle_service=oracle_service,
                timeline_projector=timeline_projector,
            )
        return tools

    @staticmethod
    def build_walk_forward_tools(
            walk_forward_service: WalkForwardApplicationService,
    ) -> Dict[str, BaseTool]:
        return {
            "walk_forward": WalkForwardTool(walk_forward_service=walk_forward_service),
        }

    @staticmethod
    def build_trace_tools(
            tick_tracer: Optional[ScheduleTickTracer] = None,
            activity_tracker: Optional[AssetActivityTracker] = None,
            decision_manager: Optional[Any] = None,
    ) -> Dict[str, BaseTool]:
        return {
            "inspect_schedule_tick_trace": TickTraceTool(
                tick_tracer=tick_tracer,
                activity_tracker=activity_tracker,
                decision_manager=decision_manager,
            ),
        }

    @staticmethod
    def build_experiment_tools(
            experiment_service: Optional[ExperimentApplicationService] = None,
            health_monitor: Optional[Any] = None,
            activity_tracker: Optional[AssetActivityTracker] = None,
            drift_detector: Optional[BacktestDriftDetector] = None,
    ) -> Dict[str, BaseTool]:
        return {
            "inspect_experiment": ExperimentInspectorTool(
                experiment_service=experiment_service,
                health_monitor=health_monitor,
                activity_tracker=activity_tracker,
                drift_detector=drift_detector,
            ),
        }

    @staticmethod
    def build_retention_tools(
            retention_manager: RetentionManager,
    ) -> Dict[str, BaseTool]:
        return {
            "inspect_retention_governance": RetentionGovernanceTool(
                retention_manager=retention_manager,
            ),
        }

    @classmethod
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    def build_tool_map(
            cls,
            managers: ManagerContainer,
            assets: list[Asset],
            trading_journal: TradingJournal,
            vcs: Optional[VCSService] = None,
            oracle_service: Optional[OracleService] = None,
            timeline_projector: Optional[TimelineProjector] = None,
            backtest_service: Optional[BacktestService] = None,
            metric_service: Optional[MetricService] = None,
            db_manager: Optional[DatabaseManager] = None,
            walk_forward_service: Optional[WalkForwardApplicationService] = None,
            tick_tracer: Optional[ScheduleTickTracer] = None,
            activity_tracker: Optional[AssetActivityTracker] = None,
            experiment_service: Optional[ExperimentApplicationService] = None,
            retention_manager: Optional[RetentionManager] = None,
    ) -> Dict[str, BaseTool]:
        tools = cls.build_core_trading_tools(
            managers=managers,
            assets=assets,
            trading_journal=trading_journal,
        )
        if vcs is not None:
            tools.update(cls.build_vcs_tools(vcs))
        if backtest_service is not None:
            tools.update(cls.build_backtest_tools(backtest_service, trading_journal))
        if metric_service is not None:
            tools.update(cls.build_metric_tools(metric_service))
        if db_manager is not None:
            config_svc = ConfigurationService(vcs) if vcs is not None else None
            tools.update(cls.build_attribution_tools(db_manager, managers.session_manager, config_svc))
        if walk_forward_service is not None:
            tools.update(cls.build_walk_forward_tools(walk_forward_service))
        if oracle_service is not None:
            tools.update(cls.build_oracle_tools(oracle_service, timeline_projector))
        if tick_tracer is not None or activity_tracker is not None:
            tools.update(
                cls.build_trace_tools(
                    tick_tracer=tick_tracer,
                    activity_tracker=activity_tracker,
                    decision_manager=managers.decision_manager,
                )
            )
        if experiment_service is not None:
            drift_det = (
                BacktestDriftDetector(backtest_service, trading_journal)
                if backtest_service is not None and trading_journal is not None
                else None
            )
            tools.update(
                cls.build_experiment_tools(
                    experiment_service=experiment_service,
                    health_monitor=managers.health_monitor,
                    activity_tracker=activity_tracker,
                    drift_detector=drift_det,
                )
            )
        if retention_manager is not None:
            tools.update(cls.build_retention_tools(retention_manager))
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
