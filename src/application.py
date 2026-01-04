from __future__ import annotations

import atexit

from queue import Queue
from threading import Event

import src.trading.consensus.strategies
import src.configuration.providers
import src.clients
import src.trading.protection.guards

from database.database_manager import DatabaseManager
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.helpers.application_helper import ApplicationHelper
from src.core.interfaces.base_config import BaseConfig
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.context.trading_context_manager import TradingContextManager
from src.trading.fees.fees_manager import FeesManager
from src.core.managers.manager_container import ManagerContainer
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.core.interfaces.exchange_rest_client import ExchangeRestClient
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
        return ManagerContainer(
            account_manager=AccountManager(self._assets),
            fees_manager=FeesManager(),
            order_manager=OrderManager(db_manager),
            market_data_manager=MarketDataManager(self._assets),
            consensus_manager=ConsensusManager(),
            protection_manager=ProtectionManager(),
            trading_context_manager=TradingContextManager(),
        )

    def _register_with_managers(self, instance: ExchangeRestClient | ExchangeWebSocketClient):
        if not isinstance(instance, (ExchangeRestClient, ExchangeWebSocketClient)):
            raise RuntimeError(f"Instance of type {type(instance)} not allowed!")
        for manager in vars(self._managers).values():
            if (isinstance(instance, ExchangeRestClient)
                    and hasattr(manager, RestClientRegistry.register_client.__name__)):
                getattr(manager, RestClientRegistry.register_client.__name__)(instance)
            if (isinstance(instance, ExchangeWebSocketClient)
                    and hasattr(manager, WebSocketRegistry.register_websocket.__name__)):
                getattr(manager, WebSocketRegistry.register_websocket.__name__)(instance)

    def _setup_clients(self):
        ApplicationHelper.import_modules(src.clients)
        for cls in ExchangeRestClient.__subclasses__():
            if cls.__module__.startswith(src.clients.__name__):
                self._register_with_managers(cls())

        for cls in ExchangeWebSocketClient.__subclasses__():
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

    def register_client(self, rest_client: ExchangeRestClient, websocket_client: ExchangeWebSocketClient):
        self._register_with_managers(rest_client)
        self._register_with_managers(websocket_client)

    def shutdown(self):
        if not self.is_running.is_set():
            return
        if self._trading_engine:
            self._trading_engine.stop_application()
        if self._managers and self._managers.order_manager:
            self._managers.order_manager.shutdown()
        self.is_running.clear()
        self.app_logger.info("Stopping Application...")
