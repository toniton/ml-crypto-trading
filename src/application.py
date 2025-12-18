import atexit
import importlib
import logging
import pkgutil

from queue import Queue
from sqlalchemy.orm import Session

from database.database_setup import DatabaseSetup
from database.unit_of_work import UnitOfWork

from api.interfaces.trading_strategy import TradingStrategy

import src.trading.consensus.strategies
import src.configuration.providers
import src.clients
import src.trading.protection.guards

from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.base_config import BaseConfig
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager

from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.trading.context.trading_context_manager import TradingContextManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.core.interfaces.exchange_rest_client import ExchangeRestClient
from src.core.interfaces.guard import Guard
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.trading.trading_scheduler import TradingScheduler


class Application:
    def __init__(
            self, activity_queue: Queue = Queue(),
            is_backtest_mode: bool = False, application_config_path: str = None,
            asset_config_path: str = None
    ):
        self.trading_engine = None
        self.activity_queue = activity_queue
        self.is_backtest_mode = is_backtest_mode
        self.unit_of_work = None
        self.environment_config = EnvironmentConfig()

        application_yaml = application_config_path if is_backtest_mode else None
        self.application_config = ApplicationConfig(_yaml_file=application_yaml)

        self._setup_configuration()
        database_session = self._setup_database()
        self.unit_of_work = UnitOfWork(database_session)

        asset_yaml = asset_config_path if is_backtest_mode else None
        assets_config = AssetsConfig(_yaml_file=asset_yaml)
        self.assets = assets_config.assets

        trading_context_manager = TradingContextManager()
        self.account_manager = AccountManager(self.assets)
        self.fees_manager = FeesManager()
        self.order_manager = OrderManager(self.unit_of_work)
        self.market_data_manager = MarketDataManager(self.assets)

        self.consensus_manager = ConsensusManager()
        self.protection_manager = ProtectionManager()

        self.trading_scheduler = TradingScheduler()
        self.trading_executor = TradingExecutor(
            self.assets, self.account_manager, self.fees_manager, self.order_manager,
            self.market_data_manager, self.consensus_manager,
            trading_context_manager, self.protection_manager, self.activity_queue
        )

        if not self.is_backtest_mode:
            self._setup_clients()

        self._setup_strategies()
        self._setup_protections()
        self._setup_asset_schedules()

        atexit.register(self.shutdown)

        print(["Crypto Dot Com API Key", self.environment_config.crypto_dot_com_exchange_api_key])
        print(["Application config", self.application_config.crypto_dot_com_exchange_rest_endpoint])
        print(["Application config", self.application_config.crypto_dot_com_exchange_websocket_endpoint])

    def _setup_configuration(self):
        for (_, name, _) in pkgutil.iter_modules(src.configuration.providers.__path__):
            try:
                importlib.import_module("." + name, src.configuration.providers.__name__)
            except ImportError as exc:
                logging.warning(f"Skipping configuration {name}: {exc}")

        for cls in BaseConfig.__subclasses__():
            cls(self.application_config, self.environment_config)

    def _setup_database(self):
        database_setup = DatabaseSetup()
        DatabaseSetup.run_migrations()
        database_setup.create_tables()
        database_engine = database_setup.create_engine()
        return Session(database_engine)

    def _setup_clients(self):
        for (_, name, _) in pkgutil.iter_modules(src.clients.__path__):
            try:
                importlib.import_module("." + name, src.clients.__name__)
            except ImportError as exc:
                logging.warning(f"Skipping client {name}: {exc}")

        for cls in ExchangeRestClient.__subclasses__():
            instance = cls()
            self.account_manager.register_provider(instance)
            self.fees_manager.register_provider(instance)
            self.order_manager.register_provider(instance)
            self.market_data_manager.register_provider(instance)

        for cls in ExchangeWebSocketClient.__subclasses__():
            instance = cls()
            self.account_manager.register_websocket(instance)
            self.order_manager.register_websocket(instance)
            self.market_data_manager.register_websocket(instance)

    def _setup_strategies(self):
        for (_, name, _) in pkgutil.iter_modules(src.trading.consensus.strategies.__path__):
            try:
                importlib.import_module("." + name, src.trading.consensus.strategies.__name__)
            except ImportError as exc:
                logging.warning(f"Skipping strategy {name}: {exc}")

        for cls in RuleBasedTradingStrategy.__subclasses__():
            instance = cls()
            self.consensus_manager.register_strategy(instance)

        # for cls in MachineLearningTradingStrategy.__subclasses__():
        #     instance = cls(prediction_engine)
        #     self.consensus_manager.register_strategy(instance)

    def _setup_protections(self):
        for (_, name, _) in pkgutil.iter_modules(src.trading.protection.guards.__path__):
            importlib.import_module("." + name, src.trading.protection.guards.__name__)

        for asset in self.assets:
            for cls in Guard.__subclasses__():
                if cls.is_enabled(asset) is True:
                    instance = cls(asset.guard_config)
                    self.protection_manager.register_guard(asset.key, instance)

    def _setup_asset_schedules(self):
        for asset in self.assets:
            self.trading_scheduler.register_asset(asset)

    def startup(self):
        self.trading_engine = TradingEngine(
            self.trading_scheduler,
            self.trading_executor
        )
        self.trading_engine.init_application()

    def register_provider(self, provider: ExchangeRestClient):
        self.order_manager.register_provider(provider)
        self.market_data_manager.register_provider(provider)

    def register_strategy(self, strategy: TradingStrategy):
        self.consensus_manager.register_strategy(strategy)

    def shutdown(self):
        # FIXME: Cancel all pending/open trades as part of application shutdown procedures.
        if self.trading_engine:
            self.trading_engine.print_context()
