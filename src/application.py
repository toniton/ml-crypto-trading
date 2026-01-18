from __future__ import annotations

import atexit

from queue import Queue
from threading import Event

import src.trading.consensus.strategies
import src.configuration.providers
import src.trading.protection.guards

from database.database_manager import DatabaseManager
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.helpers.application_helper import ApplicationHelper
from src.core.interfaces.base_config import BaseConfig
from src.clients.websocket_manager import WebSocketManager
from src.clients.rest_manager import RestManager
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.session.session_manager import SessionManager
from src.trading.fees.fees_manager import FeesManager
from src.core.managers.manager_container import ManagerContainer
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.trading.session.in_memory_trading_journal import InMemoryTradingJournal
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.guard import Guard
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor

from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.core.interfaces.trading_scheduler import TradingScheduler


class Application(ApplicationLoggingMixin):
    def __init__(
            self, application_config: ApplicationConfig, environment_config: EnvironmentConfig,
            assets_config: AssetsConfig, activity_queue: Queue = Queue(),
            is_backtest_mode: bool = False,
            backtest_scheduler: TradingScheduler = None,
    ):
        self.is_running = Event()
        self._trading_engine = None
        self._backtest_scheduler = backtest_scheduler
        self._is_backtest_mode = is_backtest_mode
        self._environment_config = environment_config
        self._application_config = application_config
        self._activity_queue = activity_queue
        self._setup_configuration()

        db_manager = DatabaseManager()
        db_manager.initialize()
        self._assets = assets_config.assets

        self._managers = self._create_managers(db_manager)

        if not self._is_backtest_mode:
            self._setup_clients()

        self._setup_strategies()
        self._setup_protections()

        atexit.register(self.shutdown)

    def _setup_configuration(self):
        ApplicationHelper.import_modules(src.configuration.providers)
        for cls in BaseConfig.__subclasses__():
            cls(self._environment_config)

    def _create_managers(self, db_manager: DatabaseManager) -> ManagerContainer:
        trading_journal = InMemoryTradingJournal()
        websocket_manager = WebSocketManager()
        rest_manager = RestManager()
        return ManagerContainer(
            account_manager=AccountManager(self._assets, rest_manager, websocket_manager),
            fees_manager=FeesManager(rest_manager),
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
        ApplicationHelper.import_modules(src.clients)
        for cls in ExchangeRestService.__subclasses__():
            if cls.__module__.startswith(src.clients.__name__):
                self._register_with_managers(cls())

        for cls in ExchangeWebSocketService.__subclasses__():
            if cls.__module__.startswith(src.clients.__name__):
                self._register_with_managers(cls())

    def _setup_strategies(self):
        ApplicationHelper.import_modules(src.trading.consensus.strategies)
        for cls in RuleBasedTradingStrategy.__subclasses__():
            instance = cls()
            self._managers.consensus_manager.register_strategy(instance)

        # for cls in MachineLearningTradingStrategy.__subclasses__():
        #     instance = cls(prediction_engine)
        #     self.consensus_manager.register_strategy(instance)

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
        trading_scheduler = self._backtest_scheduler if self._is_backtest_mode else LiveTradingScheduler()
        trading_scheduler.register_assets(self._assets)
        trading_executor = TradingExecutor(self._assets, self._managers, self._activity_queue)
        self._trading_engine = TradingEngine(trading_scheduler, trading_executor)
        self._trading_engine.start_application()

    def register_client(self, rest_service: ExchangeRestService, websocket_service: ExchangeWebSocketService):
        self._register_with_managers(rest_service)
        self._register_with_managers(websocket_service)

    def shutdown(self):
        if not self.is_running.is_set():
            return
        if self._trading_engine:
            self._trading_engine.stop_application()
        self.is_running.clear()
        self.app_logger.info("Stopping Application...")
