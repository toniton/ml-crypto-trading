from __future__ import annotations

import atexit
from queue import Queue
from threading import Event
from typing import Optional

import src.configuration.providers
import src.trading.protection.guards
import src.exchange.clients
from src.agent import AgentGateway
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.conversation_manager import ConversationManager
from src.server.server import ApiServer
from src.database.database_manager import DatabaseManager
from src.vcs.application.events import RefChangedEvent
from src.vcs.application.listener import RefChangeListener
from src.vcs.application.service import VCSService
from src.exchange.factories.client_factory import ClientFactory
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
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.managers.manager_container import ManagerContainer
from src.llm.model_factory import ModelFactory
from src.llm.tools.account_balance_tool import AccountBalanceTool
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
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.trading.llm_oracle_scheduler import LlmOracleScheduler
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.session.in_memory_trading_journal import InMemoryTradingJournal
from src.trading.session.session_manager import SessionManager
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.trading.trading_oracle import TradingOracle


class Application(ApplicationLoggingMixin):
    def __init__(
            self, application_config: ApplicationConfig, environment_config: EnvironmentConfig,
            trading_config: TradingConfig, llm_config: LlmConfig,
            activity_queue: Queue = Queue(),
            is_backtest_mode: bool = False,
            backtest_scheduler: TradingScheduler = None,
    ):
        self.is_running = Event()
        self.is_ready = Event()
        self._trading_engine = None
        self._api_server: Optional[ApiServer] = None
        self._backtest_scheduler = backtest_scheduler
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
        trading_journal = InMemoryTradingJournal()
        self._trading_journal = trading_journal
        is_simulated = self._application_config.simulated

        websocket_manager = ClientFactory.create_websocket_manager(is_simulated)
        rest_manager = ClientFactory.create_rest_manager(is_simulated)

        return ManagerContainer(
            account_manager=AccountManager(self._assets, rest_manager, websocket_manager),
            fees_manager=FeesManager(self._assets, rest_manager),
            order_manager=OrderManager(db_manager, trading_journal, rest_manager, websocket_manager),
            market_data_manager=MarketDataManager(rest_manager, websocket_manager),
            consensus_manager=ConsensusManager(),
            protection_manager=ProtectionManager(),
            session_manager=SessionManager(),
            websocket_manager=websocket_manager,
            rest_manager=rest_manager
        )

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
        if not self._is_backtest_mode:
            self._ensure_config_store_seeded()
            self._config_listener.start()
        trading_scheduler = self._backtest_scheduler if self._is_backtest_mode else LiveTradingScheduler()
        trading_scheduler.register_assets(self._assets)
        trading_executor = TradingExecutor(
            self._assets, self._managers, self._activity_queue, self._dynamic_quantity,
            strategies_registry=self._strategies_registry
        )
        oracle_scheduler = LlmOracleScheduler(self._llm_config)
        oracle_scheduler.register_assets(self._assets, self._llm_config.schedule)
        llm = ModelFactory.create_model(self._llm_config)
        trading_oracle = TradingOracle(llm)
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
        trading_oracle.register_tools([context_tool, fees_tool, market_stats_tool, open_orders_tool])

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
            ]
            api_llm.bind_tools(llm_tools)
            gateway = AgentGateway(api_llm, self._application_config.trading_config_filepath)
            conversations = ConversationManager(self._db_manager)
            self._api_server = ApiServer(
                agent=gateway,
                conversations=conversations,
                configuration_service=configuration_service,
            )
            self._api_server.start()

        self._trading_engine = TradingEngine(
            trading_scheduler, trading_executor, oracle_scheduler, trading_oracle
        )
        self._trading_engine.start_application()
        self.is_ready.set()

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
        self._config_listener.stop()
        if self._trading_engine:
            self._trading_engine.stop_application()
        self.is_running.clear()
        self.is_ready.clear()
        self.app_logger.info("Stopping Application...")
