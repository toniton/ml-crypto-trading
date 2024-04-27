#!/usr/bin/env python3
import atexit
import importlib
import os.path
import pkgutil
from queue import Queue

from sqlalchemy.orm import Session

from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.providers.base_config import BaseConfig
from database.database_setup import DatabaseSetup

from prediction.prediction_engine import PredictionEngine
from prediction.providers.local_storage_data_provider import LocalStorageDataProvider
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.consensus.interfaces.machine_learning_trading_strategy import MachineLearningTradingStrategy
from api.interfaces.trading_strategy import TradingStrategy
from api.interfaces.trading_context import TradingContext
from src.trading.consensus.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.trading.context.trading_context_manager import TradingContextManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from api.interfaces.exchange_provider import ExchangeProvider
from src.trading.protection.guard import Guard
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.trading_engine import TradingEngine
from database.unit_of_work import UnitOfWork

PREDICTION_STORAGE_DIR = os.path.join(os.path.abspath(os.getcwd()), "./localstorage")
STRATEGY_DIR = "src/trading/consensus/strategies"
CONFIG_PROVIDERS_DIR = "src/configuration/providers"
TRADING_PROVIDERS_DIR = "src/trading/providers"
PROTECTION_GUARDS_DIR = "src/trading/protection/guards"


class Application:
    def __init__(self, activity_queue: Queue):
        self.trading_engine = None
        self.activity_queue = activity_queue
        self.unit_of_work = None
        self.environment_config = EnvironmentConfig()
        self.application_config = ApplicationConfig(
            _env_file=ApplicationConfig.get_env_path(self.environment_config.app_env)
        )

        self._setup_configuration()

        self.assets_config = AssetsConfig()
        self.assets = self.assets_config.assets

        self.trading_context_manager = TradingContextManager()

        database_session = self._setup_database()
        self.unit_of_work = UnitOfWork(database_session)

        self.order_manager = OrderManager(self.unit_of_work)
        self.market_data_manager = MarketDataManager(self.assets)

        self.consensus_manager = ConsensusManager()
        self.protection_manager = ProtectionManager()

        self._setup_providers()
        self._setup_strategies()
        self._setup_protectons()
        self._setup_trading_context()

        atexit.register(self.shutdown)

        print(["Crypto Dot Com API Key", self.environment_config.crypto_dot_com_exchange_api_key])
        print(["Application config", self.application_config.crypto_dot_com_exchange_rest_endpoint])
        print(["Application config", self.application_config.crypto_dot_com_exchange_websocket_endpoint])

    def _setup_configuration(self):
        for (module_loader, name, ispkg) in pkgutil.iter_modules([CONFIG_PROVIDERS_DIR]):
            importlib.import_module("." + name, CONFIG_PROVIDERS_DIR.replace("/", "."))

        for cls in BaseConfig.__subclasses__():
            cls(self.application_config, self.environment_config)

    def _setup_database(self):
        database_setup = DatabaseSetup()
        database_setup.create_tables()
        database_engine = database_setup.create_engine()
        return Session(database_engine)

    def _setup_providers(self):
        for (module_loader, name, ispkg) in pkgutil.iter_modules([TRADING_PROVIDERS_DIR]):
            importlib.import_module("." + name, TRADING_PROVIDERS_DIR.replace("/", "."))

        for cls in ExchangeProvider.__subclasses__():
            instance = cls()
            self.order_manager.register_provider(instance)
            self.market_data_manager.register_provider(instance)

    def _setup_strategies(self):
        localstorage_provider = LocalStorageDataProvider(PREDICTION_STORAGE_DIR)
        prediction_engine = PredictionEngine(self.assets, localstorage_provider, PREDICTION_STORAGE_DIR)
        prediction_engine.load_assets_model()

        for (module_loader, name, ispkg) in pkgutil.iter_modules([STRATEGY_DIR]):
            importlib.import_module("." + name, STRATEGY_DIR.replace("/", "."))

        for cls in RuleBasedTradingStrategy.__subclasses__():
            instance = cls()
            self.consensus_manager.register_strategy(instance)

        for cls in MachineLearningTradingStrategy.__subclasses__():
            instance = cls(prediction_engine)
            self.consensus_manager.register_strategy(instance)

    def _setup_protectons(self):
        for (module_loader, name, ispkg) in pkgutil.iter_modules([PROTECTION_GUARDS_DIR]):
            importlib.import_module("." + name, PROTECTION_GUARDS_DIR.replace("/", "."))

        for asset in self.assets:
            for cls in Guard.__subclasses__():
                if cls.is_enabled(asset) is True:
                    instance = cls(asset.guard_config)
                    self.protection_manager.register_guard(asset.ticker_symbol, instance)

    def _setup_trading_context(self):
        for asset in self.assets:
            name = asset.name
            exchange = asset.exchange
            ticker_symbol = asset.ticker_symbol
            opening_balance = float(input(f"Set opening balance for {name} - {ticker_symbol} at {exchange.value}"))
            self.trading_context_manager.register_trading_context(ticker_symbol, TradingContext(starting_balance=opening_balance))

    def startup(self):
        self.trading_engine = TradingEngine(
            self.assets, self.order_manager,
            self.market_data_manager, self.consensus_manager,
            self.trading_context_manager,
            self.protection_manager,
            self.activity_queue
        )
        self.trading_engine.init_application()

    def register_provider(self, provider: ExchangeProvider):
        self.order_manager.register_provider(provider)
        self.market_data_manager.register_provider(provider)

    def register_strategy(self, strategy: TradingStrategy):
        self.consensus_manager.register_strategy(strategy)

    def shutdown(self):
        self.trading_engine.print_context()

    pass
