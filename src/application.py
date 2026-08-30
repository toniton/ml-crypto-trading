from __future__ import annotations

import atexit
from decimal import Decimal
from queue import Queue
from threading import Event
from typing import Optional

import src.configuration.providers
import src.trading.protection.guards
import src.exchange.clients
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.agent import AgentGateway
from src.agent.backtest.backtest_service import BacktestService
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.oracle import (
    AnalyzeTradingStateTool,
    GetTradingSummaryTool,
    OracleContext,
    OracleService,
    summary_interval_for,
)
from src.backtest.runner.backtest_runner import BacktestRunner
from src.server.server import ApiServer
from src.database.database_manager import DatabaseManager
from src.vcs.application.events import RefChangedEvent
from src.vcs.application.listener import RefChangeListener
from src.vcs.application.service import VCSService
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.llm_config import LlmConfig
from src.configuration.helpers.application_helper import ApplicationHelper
from src.configuration.strategies_config import StrategiesConfig
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.base_config import BaseConfig
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.guard import Guard
from src.events.message_event_bus import MessageEventBus
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.logging.manager import LoggingManager
from src.trading.managers.manager_container import ManagerContainer
from src.trading.managers.manager_factory import ManagerFactory
from src.llm.model_factory import ModelFactory
from src.llm.tools.account_balance_tool import AccountBalanceTool
from src.llm.tools.backtest_tool import BacktestTool
from src.llm.tools.configuration_history_tool import ConfigurationHistoryTool
from src.llm.tools.configuration_tool import ConfigurationTool
from src.llm.tools.consensus_tool import ConsensusTool
from src.llm.tools.exchange_fees_tool import ExchangeFeesTool
from src.llm.tools.market_statistics_tool import MarketStatisticsTool
from src.llm.tools.open_orders_tool import GetOpenOrdersTool
from src.llm.tools.position_tool import PositionTool
from src.llm.tools.recent_trades_tool import RecentTradesTool
from src.llm.tools.session_summary_tool import SessionSummaryTool
from src.llm.tools.strategy_votes_tool import StrategyVotesTool
from src.llm.tools.trading_context_tool import TradingContextTool
from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.trading.orders.order_reconciler import OrderReconciler
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor


class Application(ApplicationLoggingMixin):
    def __init__(
            self, application_config: ApplicationConfig, environment_config: EnvironmentConfig,
            trading_config: TradingConfig, llm_config: LlmConfig,
            activity_queue: Queue = Queue(),
            is_backtest_mode: bool = False,
    ):
        self.is_running = Event()
        self.is_ready = Event()
        self._trading_engine = None
        self._api_server: Optional[ApiServer] = None
        self._event_bus: Optional[MessageEventBus] = None
        self._trading_event_bus: Optional[MessageEventBus] = None
        self._oracle_service: Optional[OracleService] = None
        self._is_backtest_mode = is_backtest_mode
        self._environment_config = environment_config
        self._application_config = application_config
        self._activity_queue = activity_queue
        self._setup_configuration()

        db_manager = DatabaseManager()
        db_manager.initialize()
        self._db_manager = db_manager
        self._assets = trading_config.assets
        self._dynamic_quantity = trading_config.dynamic_quantity
        self._llm_config = llm_config
        self._trading_config = trading_config
        self._strategies_config = StrategiesConfig()
        self._strategies_registry = StrategyRegistry(self._strategies_config.strategies)

        self._vcs_ref = "HEAD"
        self._vcs = VCSService(db_manager)
        self._config_listener = RefChangeListener(
            db_manager=db_manager,
            on_event_callback=self._on_vcs_ref_change,
            config_vcs=self._vcs,
        )

        self._managers = self._create_managers(db_manager)

        if not self._is_backtest_mode:
            self._setup_clients()

        self._setup_protections()

        atexit.register(self.shutdown)

    def _setup_configuration(self):
        ApplicationHelper.import_modules(src.configuration.providers)
        for cls in BaseConfig.__subclasses__():
            cls(self._environment_config)

    def _create_managers(self, db_manager: DatabaseManager) -> ManagerContainer:
        is_simulated = self._application_config.simulated

        container, trading_journal = ManagerFactory.build_manager_container(
            db_manager, self._assets, is_simulated
        )
        self._trading_journal = trading_journal
        self._order_reconciler = OrderReconciler(container.order_manager)
        container.websocket_manager.set_reconnect_callback(self._order_reconciler.trigger)

        return container

    def _register_with_managers(self, instance: ExchangeRestService | ExchangeWebSocketService):
        if not isinstance(instance, (ExchangeRestService, ExchangeWebSocketService)):
            raise RuntimeError(f"Instance of type {type(instance)} not allowed!")

        if isinstance(instance, ExchangeRestService):
            self._managers.rest_manager.register_service(instance)
        if isinstance(instance, ExchangeWebSocketService):
            self._managers.websocket_manager.register_service(instance)

    def _setup_clients(self):
        ApplicationHelper.import_modules(src.exchange.clients)

        self._setup_service_clients(ExchangeRestService)
        self._setup_service_clients(ExchangeWebSocketService)

    def _setup_service_clients(
            self, service_class: type[ExchangeRestService | ExchangeWebSocketService]
    ):
        for cls in service_class.__subclasses__():
            if cls.__module__.startswith(src.exchange.clients.__name__):
                if hasattr(cls, 'get_supported_providers') and callable(cls.get_supported_providers):
                    for provider in cls.get_supported_providers():
                        instance = cls(provider)
                        self._register_with_managers(instance)

    def _setup_protections(self):
        ApplicationHelper.import_modules(src.trading.protection.guards)
        for asset in self._assets:
            for cls in Guard.__subclasses__():
                if cls.is_enabled(asset) is True:
                    instance = cls(asset.guard_config)
                    self._managers.protection_manager.register_guard(asset.key, instance)

    def startup(self):
        if self.is_running.is_set():
            return
        self.app_logger.info("Starting Application...")
        self.is_running.set()
        if self._is_backtest_mode:
            self.is_ready.set()
            return

        self._ensure_config_store_seeded()
        self._config_listener.start()

        trading_scheduler = LiveTradingScheduler()
        trading_scheduler.register_assets(self._assets)
        self._trading_event_bus = MessageEventBus()
        trading_executor = TradingExecutor(
            self._assets, self._managers, self._activity_queue, self._dynamic_quantity,
            strategies_registry=self._strategies_registry,
            event_bus=self._trading_event_bus,
        )
        self._setup_live_engine(trading_scheduler, trading_executor)

        self._trading_engine.start_application()
        self._order_reconciler.start()
        self.is_ready.set()

    def _setup_live_engine(self, trading_scheduler, trading_executor):
        context_tool = TradingContextTool(
            session_manager=self._managers.session_manager
        )
        fees_tool = ExchangeFeesTool(
            fees_manager=self._managers.fees_manager,
            assets=self._assets
        )
        market_stats_tool = MarketStatisticsTool(
            market_data_manager=self._managers.market_data_manager,
            assets=self._assets
        )
        open_orders_tool = GetOpenOrdersTool(
            order_manager=self._managers.order_manager,
            assets=self._assets
        )

        llm = ModelFactory.create_model(self._llm_config)
        oracle_context = OracleContext(
            summary_interval=summary_interval_for(self._llm_config.schedule),
        )
        oracle_service = OracleService(
            llm,
            oracle_context,
            publish_bus=self._trading_event_bus,
            model=self._llm_config.default_model.name,
            model_version=self._llm_config.default_model.model_name,
        )
        oracle_service.subscribe(self._trading_event_bus)
        self._oracle_service = oracle_service

        self._trading_engine = TradingEngine(trading_scheduler, trading_executor)

        if not self._application_config.headless:
            api_llm = ModelFactory.create_model(self._llm_config)
            configuration_service = ConfigurationService(
                self._application_config.trading_config_filepath,
                vcs=self._vcs,
            )
            account_balance_tool = AccountBalanceTool(
                account_manager=self._managers.account_manager,
                assets=self._assets,
            )
            position_tool = PositionTool(
                session_manager=self._managers.session_manager,
                assets=self._assets,
            )
            recent_trades_tool = RecentTradesTool(
                trading_journal=self._trading_journal,
                assets=self._assets,
            )
            consensus_tool = ConsensusTool(
                consensus_manager=self._managers.consensus_manager,
                session_manager=self._managers.session_manager,
                market_data_manager=self._managers.market_data_manager,
                assets=self._assets,
            )
            strategy_votes_tool = StrategyVotesTool(
                consensus_manager=self._managers.consensus_manager,
                session_manager=self._managers.session_manager,
                market_data_manager=self._managers.market_data_manager,
                assets=self._assets,
            )
            configuration_tool = ConfigurationTool(configuration_service=configuration_service)
            configuration_history_tool = ConfigurationHistoryTool(vcs=self._vcs)
            session_summary_tool = SessionSummaryTool(session_manager=self._managers.session_manager)
            get_trading_summary_tool = GetTradingSummaryTool(oracle_service=self._oracle_service)
            analyze_trading_state_tool = AnalyzeTradingStateTool(oracle_service=self._oracle_service)
            backtest_tool = BacktestTool(backtest_service=self._build_backtest_service())

            llm_tools = [
                context_tool,
                fees_tool,
                market_stats_tool,
                open_orders_tool,
                account_balance_tool,
                position_tool,
                recent_trades_tool,
                consensus_tool,
                strategy_votes_tool,
                configuration_tool,
                configuration_history_tool,
                session_summary_tool,
                get_trading_summary_tool,
                analyze_trading_state_tool,
                backtest_tool,
            ]
            api_llm.bind_tools(llm_tools)
            gateway = AgentGateway(
                api_llm,
                self._application_config.trading_config_filepath,
                vcs=self._vcs,
            )
            self._event_bus = MessageEventBus()
            LoggingManager.get_instance().set_event_bus(self._event_bus)
            self._api_server = ApiServer(
                agent=gateway,
                event_bus=self._event_bus,
                db_manager=self._db_manager,
            )
            self._api_server.start()

    def run_backtest(self) -> None:
        """Drive the backtest simulation(s) via a BacktestRunner."""

        requests = [self._build_backtest_request(asset) for asset in self._assets]
        results = self._build_backtest_runner().run(requests)
        for result in results:
            self.app_logger.info(
                f"Backtest {result.session_id} for {result.ticker_symbol}: "
                f"initial={result.initial_balance} final_equity={result.final_equity} "
                f"fills={len(result.fills)} orders={len(result.orders)}"
            )

    def _build_backtest_runner(self) -> BacktestRunner:
        return BacktestRunner(
            self._db_manager,
            {asset.ticker_symbol: asset for asset in self._assets},
            self._strategies_registry,
            self._activity_queue,
            self._dynamic_quantity,
        )

    def _build_backtest_service(self) -> BacktestService:
        data_source_request = BacktestDataSourceRequest(
            source_type=BacktestDataSourceType.CSV,
            path=self._application_config.historical_data_dir_path,
        )
        return BacktestService(
            self._build_backtest_runner(),
            data_source_request=data_source_request,
            initial_balance=self._application_config.backtest_initial_balance,
            execution=ExecutionConfiguration(
                latency_ms=self._application_config.backtest_latency_ms,
                slippage_ticks=self._application_config.backtest_slippage_ticks,
                fee_rate=Decimal(str(self._application_config.backtest_fee_rate)),
            ),
        )

    def _build_backtest_request(self, asset) -> BacktestRequest:
        return BacktestRequest(
            ticker_symbol=asset.ticker_symbol,
            data_source=BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV,
                path=self._application_config.historical_data_dir_path,
            ),
            initial_balance=self._application_config.backtest_initial_balance,
            execution=ExecutionConfiguration(
                latency_ms=self._application_config.backtest_latency_ms,
                slippage_ticks=self._application_config.backtest_slippage_ticks,
                fee_rate=Decimal(str(self._application_config.backtest_fee_rate)),
            ),
        )

    def register_client(self, rest_service: ExchangeRestService, websocket_service: ExchangeWebSocketService):
        self._register_with_managers(rest_service)
        self._register_with_managers(websocket_service)

    def _ensure_config_store_seeded(self) -> None:
        self._vcs.seed_if_empty(
            self._trading_config,
            author="application-bootstrap",
            message="Initial configuration committed at application start",
        )

    def _on_vcs_ref_change(self, event: RefChangedEvent) -> None:
        if event.ref != self._vcs_ref:
            return
        self._apply_config_update(event.commit_hash)

    def _apply_config_update(self, commit_hash: str) -> None:
        try:
            raw = self._vcs.checkout(commit_hash)
            updated = TradingConfig.model_validate(raw)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error("Config update from VCS failed: %s", exc)
            return

        if self._trading_engine:
            self._trading_engine.update_config(updated)
        self.app_logger.info("Config updated from VCS %s", commit_hash[:8])

    def shutdown(self):
        if not self.is_running.is_set():
            return
        if self._api_server:
            self._api_server.stop()
            self._api_server = None
        if self._event_bus:
            self._event_bus.close()
            self._event_bus = None
        if self._trading_event_bus:
            self._trading_event_bus.close()
            self._trading_event_bus = None
        self._oracle_service = None
        self._config_listener.stop()
        if self._order_reconciler:
            self._order_reconciler.stop()
        if self._trading_engine:
            self._trading_engine.stop_application()
        self.is_running.clear()
        self.is_ready.clear()
        self.app_logger.info("Stopping Application...")
