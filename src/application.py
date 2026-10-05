from __future__ import annotations

import atexit
from decimal import Decimal
from queue import Queue
from threading import Event
from typing import Optional

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
import src.configuration.providers
import src.exchange.clients
import src.trading.protection.guards
from src.exchange.network import enforce_ipv4
from src.agent import AgentGateway
from src.agent.actions import (
    AgentActionExecutor,
    AgentActionService,
    AgentApprovalService,
)
from src.agent.automation import AutomationController, InvestigateActivityAnomaly
from src.agent.backtest.backtest_service import BacktestService
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.agent.oracle import (
    OracleContext,
    OracleService,
    summary_interval_for,
)
from src.agent.runtime_debug.incident_aggregator import IncidentAggregator
from src.agent.runtime_debug.service import RuntimeDebugService
from src.backtest.analysis.drift_detector import BacktestDriftDetector
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.helpers.application_helper import ApplicationHelper
from src.configuration.llm_config import LlmConfig
from src.configuration.strategies_config import StrategiesConfig
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.base_config import BaseConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.guard import Guard
from src.database.noop_database_manager import NoopDatabaseManager
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.llm import LlmRuntimeManager, ToolFactory
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.logging.manager import LoggingManager
from src.metrics.collectors.event_metric_collector import EventMetricCollector
from src.metrics.collectors.order_lifecycle_collector import OrderLifecycleCollector
from src.metrics.collectors.runtime_metrics_collector import RuntimeMetricsCollector
from src.metrics.collectors.trading_metrics_collector import TradingMetricsCollector
from src.metrics.services.metric_service import MetricService
from src.metrics.services.retention_engine import RetentionEngine
from src.metrics.services.retention_scheduler import RetentionScheduler
from src.recorder.market_data_recorder import MarketDataRecorder
from src.recorder.market_data_store import MarketDataStore
from src.server.server import ApiServer
from src.server.services.conversation_service import ConversationService
from src.server.services.dataset_service import DatasetService
from src.server.timeline_projector import TimelineProjector
from src.trading.activity import AssetActivityTracker
from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.trading.managers.manager_container import ManagerContainer
from src.trading.managers.manager_factory import ManagerFactory
from src.trading.orders.order_reconciler import OrderReconciler
from src.trading.reconciliation.exchange_reconciliation_engine import (
    ExchangeReconciliationEngine,
)
from src.core.interfaces.trading_engine_proxy import TradingEngineProxy
from src.trading.local_trading_engine_proxy import LocalTradingEngineProxy
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.vcs.application.events import RefChangedEvent
from src.vcs.application.listener import RefChangeListener
from src.vcs.application.service import VCSService


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
        self._trading_engine_proxy: Optional[TradingEngineProxy] = None
        self._api_server: Optional[ApiServer] = None
        self._event_bus: Optional[MessageEventBus] = None
        self._trading_event_bus = MessageEventBus()
        self._oracle_service: Optional[OracleService] = None
        self._timeline_projector: Optional[TimelineProjector] = None
        self._approval_service: Optional[AgentApprovalService] = None
        self._is_backtest_mode = is_backtest_mode
        self._environment_config = environment_config
        self._application_config = application_config
        self._seed_trading_config = trading_config
        self._trading_config: Optional[TradingConfig] = None
        self._llm_config = llm_config
        self._activity_queue = activity_queue
        self._market_data_store = MarketDataStore()
        self._market_data_recorder = MarketDataRecorder(self._market_data_store)
        self._db_manager: Optional[DatabaseManager] = None
        self._metric_service: Optional[MetricService] = None
        self._retention_engine: Optional[RetentionEngine] = None
        self._retention_scheduler: Optional[RetentionScheduler] = None
        self._event_metric_collector: Optional[EventMetricCollector] = None
        self._trading_metrics_collector: Optional[TradingMetricsCollector] = None
        self._order_lifecycle_collector: Optional[OrderLifecycleCollector] = None
        self._runtime_metrics_collector: Optional[RuntimeMetricsCollector] = None
        self._strategies_config: Optional[StrategiesConfig] = None
        self._strategies_registry: Optional[StrategyRegistry] = None
        self._vcs_ref = "HEAD"
        self._vcs: Optional[VCSService] = None
        self._managers: Optional[ManagerContainer] = None
        self._runtime_debug_service: Optional[RuntimeDebugService] = None
        self._incident_aggregator: Optional[IncidentAggregator] = None
        self._assets = []
        self._dynamic_quantity = None
        self._config_listener: Optional[RefChangeListener] = None
        self._trading_journal = None
        self._reconciliation_engine: Optional[ExchangeReconciliationEngine] = None
        self._order_reconciler: Optional[OrderReconciler] = None
        self._activity_tracker: Optional[AssetActivityTracker] = None
        self._agent_action_executor: Optional[AgentActionExecutor] = None
        self._automation: Optional[AutomationController] = None
        self._conversation_service: Optional[ConversationService] = None
        self._llm_manager: Optional[LlmRuntimeManager] = None
        self._event_bus: Optional[EventBus] = None

        atexit.register(self.shutdown)

    def _setup_configuration(self):
        ApplicationHelper.import_modules(src.configuration.providers)
        for cls in BaseConfig.__subclasses__():
            cls(self._environment_config)

    def _create_managers(self, db_manager: DatabaseManager) -> ManagerContainer:
        is_simulated = self._application_config.simulated

        container, trading_journal = ManagerFactory.build_manager_container(
            db_manager,
            self._assets,
            is_simulated,
            event_bus=self._trading_event_bus,
            metric_service=self._metric_service,
            config_vcs=self._vcs,
        )
        self._trading_journal = trading_journal
        self._order_lifecycle_collector = OrderLifecycleCollector(self._metric_service, db_manager)
        self._reconciliation_engine = container.reconciliation_engine or ExchangeReconciliationEngine.create(
            account_manager=container.account_manager,
            order_manager=container.order_manager,
            session_manager=container.session_manager,
            fees_manager=container.fees_manager,
            rest_manager=container.rest_manager,
            assets=self._assets,
            event_bus=self._trading_event_bus,
            protection_manager=container.protection_manager,
            order_lifecycle_collector=self._order_lifecycle_collector,
        )
        self._order_reconciler = self._reconciliation_engine
        container.websocket_manager.set_reconnect_callback(self._reconciliation_engine.trigger)

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
                for provider in cls.get_supported_providers():
                    instance = cls(provider)
                    self._register_with_managers(instance)

    def _setup_protections(self):
        ApplicationHelper.import_modules(src.trading.protection.guards)
        for asset in self._assets:
            for cls in Guard.__subclasses__():
                if cls.is_enabled(asset) is True:
                    instance = cls(asset.guard_config)
                    if hasattr(instance, "set_engine") and self._reconciliation_engine:
                        instance.set_engine(self._reconciliation_engine)
                    self._managers.protection_manager.register_guard(asset.key, instance)

    def startup(self):
        if self.is_running.is_set():
            return
        self.app_logger.info("Starting Application...")
        self.is_running.set()

        self._setup_configuration()

        db_manager: DatabaseManager
        try:
            db_manager = SqlAlchemyDatabaseManager()
            db_manager.initialize()
        except Exception as exc:  # pylint: disable=broad-except
            if self._is_backtest_mode:
                self.app_logger.warning(
                    f"Could not initialize SQL database in backtest mode; falling back to NoopDatabaseManager: {exc}"
                )
                db_manager = NoopDatabaseManager()
                db_manager.initialize()
            else:
                raise
        self._db_manager = db_manager
        self._metric_service = MetricService(db_manager)
        self._event_metric_collector = EventMetricCollector(self._metric_service)
        self._trading_metrics_collector = TradingMetricsCollector(self._metric_service)
        self._strategies_config = StrategiesConfig()
        self._strategies_registry = StrategyRegistry(self._strategies_config.strategies)

        if self._is_backtest_mode:
            self._assets = self._seed_trading_config.assets
            self._dynamic_quantity = self._seed_trading_config.dynamic_quantity
            self._trading_config = self._seed_trading_config
            self.is_ready.set()
            return

        self._retention_engine = RetentionEngine(db_manager)
        self._retention_scheduler = RetentionScheduler(self._retention_engine)
        self._runtime_metrics_collector = RuntimeMetricsCollector(self._metric_service)

        self._vcs_ref = "HEAD"
        self._vcs = VCSService(db_manager)

        active_config = self._resolve_active_config()
        self._assets = active_config.assets
        self._dynamic_quantity = active_config.dynamic_quantity
        self._trading_config = active_config

        self._startup_live(db_manager)

    def _resolve_active_config(self) -> TradingConfig:
        self._ensure_config_store_seeded(self._seed_trading_config)
        try:
            raw_config = self._vcs.checkout(self._vcs_ref)
            return TradingConfig.model_validate(raw_config)
        except Exception:
            return self._seed_trading_config

    def _startup_live(self, db_manager: DatabaseManager) -> None:
        enforce_ipv4()
        self._config_listener = RefChangeListener(
            db_manager=db_manager,
            on_event_callback=self._on_vcs_ref_change,
            config_vcs=self._vcs,
        )
        self._managers = self._create_managers(db_manager)
        self._setup_clients()
        self._setup_protections()
        self._config_listener.start()

        self._event_bus = MessageEventBus()
        LoggingManager.get_instance().set_event_bus(self._event_bus)

        self._runtime_debug_service = RuntimeDebugService(
            database_manager=db_manager,
            vcs=self._vcs,
            event_bus=self._trading_event_bus,
        )
        self._incident_aggregator = IncidentAggregator(
            database_manager=db_manager,
            event_bus=self._trading_event_bus,
            investigation_callback=self._runtime_debug_service.investigate_incident,
            auto_investigate=True,
        )
        self._incident_aggregator.subscribe(self._trading_event_bus)

        self._setup_agent_automation()

        trading_scheduler = LiveTradingScheduler()
        trading_scheduler.register_assets(self._assets)
        self._market_data_recorder.subscribe(self._trading_event_bus)
        self._event_metric_collector.subscribe(self._trading_event_bus)
        self._trading_metrics_collector.subscribe(self._trading_event_bus)
        self._retention_scheduler.start()
        trading_executor = TradingExecutor(
            assets=self._assets,
            manager_container=self._managers,
            activity_queue=self._activity_queue,
            dynamic_quantity=self._dynamic_quantity,
            strategies_registry=self._strategies_registry,
            event_bus=self._trading_event_bus,
        )
        self._setup_live_engine(trading_scheduler, trading_executor)

        self._trading_engine.start_application()
        if self._reconciliation_engine:
            self._reconciliation_engine.start()
        self.is_ready.set()


    def _setup_live_engine(self, trading_scheduler, trading_executor):
        backtest_service = self._build_backtest_service()
        timeline_projector = TimelineProjector(
            event_bus=self._trading_event_bus,
            db_manager=self._db_manager,
        )
        timeline_projector.subscribe()
        self._timeline_projector = timeline_projector

        tool_map = ToolFactory.build_tool_map(
            managers=self._managers,
            assets=self._assets,
            trading_journal=self._trading_journal,
            vcs=self._vcs,
            oracle_service=None,
            timeline_projector=self._timeline_projector,
            backtest_service=backtest_service,
            metric_service=self._metric_service,
            db_manager=self._db_manager,
        )
        self._llm_manager = LlmRuntimeManager(
            llm_config=self._llm_config,
            db_manager=self._db_manager,
            tool_map=tool_map,
        )

        oracle_context = OracleContext(
            summary_interval=summary_interval_for(self._llm_config.schedule),
        )
        oracle_service = OracleService(
            self._llm_manager.proxy_adapter,
            oracle_context,
            publish_bus=self._trading_event_bus,
            model=self._llm_config.default_model.name,
            model_version=self._llm_config.default_model.model_name,
        )
        oracle_service.subscribe(self._trading_event_bus)
        self._oracle_service = oracle_service

        # Update tools with oracle service
        full_tool_map = ToolFactory.build_tool_map(
            managers=self._managers,
            assets=self._assets,
            trading_journal=self._trading_journal,
            vcs=self._vcs,
            oracle_service=self._oracle_service,
            timeline_projector=self._timeline_projector,
            backtest_service=backtest_service,
            metric_service=self._metric_service,
            db_manager=self._db_manager,
        )
        self._llm_manager.update_tool_map(full_tool_map)

        self._trading_engine = TradingEngine(trading_scheduler, trading_executor)
        self._trading_engine_proxy = LocalTradingEngineProxy(
            trading_engine=self._trading_engine,
            market_data_store=self._market_data_store,
            compare_backtest=(
                self._agent_action_executor.compare_backtest_drift
                if self._agent_action_executor else (lambda action: None)
            ),
        )

        if not self._application_config.headless:
            gateway = AgentGateway(
                self._llm_manager.proxy_adapter,
                vcs=self._vcs,
                approval_service=self._approval_service,
                timeline_projector=self._timeline_projector,
            )
            self._api_server = ApiServer(
                trading_proxy=self._trading_engine_proxy,
                agent=gateway,
                event_bus=self._event_bus,
                db_manager=self._db_manager,
                vcs=self._vcs,
                llm_manager=self._llm_manager,
                host=self._application_config.api_host,
                port=self._application_config.api_port,
            )
            self._api_server.start()

    def _setup_agent_automation(self) -> None:
        """Assembles and starts the agent automation subsystem (headless-capable)."""
        self._activity_tracker = AssetActivityTracker()
        self._activity_tracker.subscribe(self._trading_event_bus)

        configuration_service = ConfigurationService(vcs=self._vcs)
        action_service = AgentActionService(event_bus=self._event_bus)
        approval_service = AgentApprovalService(
            vcs=self._vcs,
            configuration_service=configuration_service,
            action_service=action_service,
            event_bus=self._event_bus,
            conversation_store=self._conversation_service,
        )
        self._approval_service = approval_service
        try:
            backtest_service = self._build_backtest_service()
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(
                f"Backtest service unavailable; drift detection disabled: {exc}"
            )
            backtest_service = None
        self._agent_action_executor = AgentActionExecutor(
            action_service=action_service,
            approval_service=approval_service,
            vcs=self._vcs,
            configuration_service=configuration_service,
            backtest_service=backtest_service,
        )
        drift_detector = (
            BacktestDriftDetector(backtest_service, self._trading_journal)
            if backtest_service is not None else None
        )
        investigation = InvestigateActivityAnomaly(
            activity_provider=self._activity_tracker,
            drift_detector=drift_detector,
            event_bus=self._event_bus,
        )
        watchdog = StarvationWatchdog(
            activity_provider=self._activity_tracker,
            assets=self._assets,
            event_bus=self._event_bus,
            poll_interval_seconds=30.0,
        )
        self._automation = AutomationController(
            event_bus=self._event_bus,
            executor=self._agent_action_executor,
            approval_service=approval_service,
            investigation=investigation,
            watchdog=watchdog,
        )
        self._automation.start()
        self.app_logger.info("Agent automation initialized (%d assets)", len(self._assets))

    def run_backtest(self) -> None:
        """Drive the backtest simulation(s) via a BacktestService."""

        service = self._build_backtest_service()
        requests = [self._build_backtest_request(asset) for asset in self._assets]
        for request in requests:
            result = service.run(request)
            self.app_logger.info(
                f"Backtest {result.session_id} for {result.ticker_symbol}: "
                f"initial={result.initial_balance} final_equity={result.final_equity} "
                f"fills={len(result.fills)} orders={len(result.orders)}"
            )

    def _build_backtest_runner(self) -> BacktestRunner:
        return BacktestRunner(
            assets={asset.ticker_symbol: asset for asset in self._assets},
            strategy_registry=self._strategies_registry,
            activity_queue=self._activity_queue,
            dynamic_quantity=self._dynamic_quantity,
            data_source_resolver=BacktestDataSourceResolver(
                market_data_store=self._market_data_store,
                dataset_service=DatasetService(),
            ),
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
            db_manager=self._db_manager,
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

    def _ensure_config_store_seeded(self, seed_config: TradingConfig) -> None:
        self._vcs.seed_if_empty(
            seed_config,
            author="application-bootstrap",
            message="Initial configuration committed at application start",
        )

    def _on_vcs_ref_change(self, event: RefChangedEvent) -> None:
        if event.ref != self._vcs_ref:
            return
        self._apply_config_update(event.commit_hash)
        if self._event_bus is not None:
            self._event_bus.publish(event)

    def _apply_config_update(self, commit_hash: str) -> None:
        try:
            raw = self._vcs.checkout(commit_hash)
            updated = TradingConfig.model_validate(raw)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error("Config update from VCS failed: %s", exc)
            return

        if self._trading_engine_proxy is not None:
            self._trading_engine_proxy.update_config(updated)
        elif self._trading_engine is not None:
            self._trading_engine.update_config(updated)
        try:
            if self._managers and self._managers.session_manager:
                self._managers.session_manager.update_commit_hash(commit_hash)
        except AttributeError:
            pass
        self.app_logger.info("Config updated from VCS %s", commit_hash[:8])

    def shutdown(self):
        if not self.is_running.is_set():
            return
        if self._api_server:
            self._api_server.stop()
            self._api_server = None
        if self._automation:
            self._automation.stop()
            self._automation = None
        if self._event_bus:
            self._event_bus.close()
            self._event_bus = None
        if self._trading_event_bus:
            self._trading_event_bus.close()
            self._trading_event_bus = None
        if self._timeline_projector:
            self._timeline_projector.close()
            self._timeline_projector = None
        self._oracle_service = None
        if self._config_listener:
            self._config_listener.stop()
            self._config_listener = None
        if self._retention_scheduler:
            self._retention_scheduler.stop()
            self._retention_scheduler = None
        if self._runtime_metrics_collector:
            self._runtime_metrics_collector.stop_monitoring()
        if self._reconciliation_engine:
            self._reconciliation_engine.stop()
        if self._trading_engine:
            self._trading_engine.stop_application()

        self.is_running.clear()
        self.is_ready.clear()
        self.app_logger.info("Stopping Application...")
