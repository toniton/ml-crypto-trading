#!/usr/bin/env python3
import atexit
import importlib
import os.path
import pkgutil
from queue import Queue

from sqlalchemy.orm import Session

from configuration.application_config import ApplicationConfig
from configuration.assets_config import AssetsConfig
from configuration.environment_config import EnvironmentConfig
from database.database_setup import DatabaseSetup

from prediction.prediction_engine import PredictionEngine
from prediction.providers.local_storage_data_provider import LocalStorageDataProvider
from trading.consensus.consensus_manager import ConsensusManager
from trading.consensus.interfaces.machine_learning_trading_strategy import MachineLearningTradingStrategy
from api.interfaces.trading_strategy import TradingStrategy
from api.interfaces.trading_context import TradingContext
from trading.consensus.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from trading.context.trading_context_manager import TradingContextManager
from trading.mappers.cryptodotcom_marketdata_mapper import CryptoDotComMarketDataMapper
from api.interfaces.mapper import Mapper
from trading.mappers.mapper_manager import MapperManager
from trading.markets.market_data_manager import MarketDataManager
from trading.orders.order_manager import OrderManager
from trading.providers.cryptodotcom_provider import CryptoDotComProvider
from api.interfaces.exchange_provider import ExchangeProvider
from trading.trading_engine import TradingEngine
from database.unit_of_work import UnitOfWork

PREDICTION_STORAGE_DIR = os.path.join(os.path.abspath(os.getcwd()), "./localstorage")
STRATEGY_DIR = "trading/consensus/strategies"


class Application:
    def __init__(self, activity_queue: Queue):
        self.activity_queue = activity_queue
        self.unit_of_work = None
        self.environment_config = EnvironmentConfig()
        self.application_config = ApplicationConfig(
            _env_file=ApplicationConfig.get_env_path(self.environment_config.app_env)
        )

        self.assets_config = AssetsConfig()
        self.assets = self.assets_config.assets

        self.trading_context_manager = TradingContextManager()

        database_session = self._setup_database()
        self.unit_of_work = UnitOfWork(database_session)

        self.order_manager = OrderManager(self.unit_of_work)
        self.mapper_manager = MapperManager()
        self.market_data_manager = MarketDataManager(self.assets)

        self.consensus_manager = ConsensusManager()

        self._setup_providers()
        self._setup_strategies()
        self._setup_trading_context()

        atexit.register(self.shutdown)

        print(["Crypto Dot Com API Key", self.environment_config.crypto_dot_com_exchange_api_key])
        print(["Application config", self.application_config.crypto_dot_com_exchange_rest_endpoint])
        print(["Application config", self.application_config.crypto_dot_com_exchange_websocket_endpoint])

    def _setup_database(self):
        database_setup = DatabaseSetup(self.environment_config, self.application_config)
        database_setup.create_tables()
        database_engine = database_setup.create_engine()
        return Session(database_engine)

    def _setup_providers(self):
        cryptodotcom_provider = CryptoDotComProvider(
            self.application_config.crypto_dot_com_exchange_rest_endpoint,
            self.application_config.crypto_dot_com_exchange_websocket_endpoint,
            self.environment_config.crypto_dot_com_exchange_api_key,
            self.environment_config.crypto_dot_com_exchange_secret_key
        )
        self.order_manager.register_provider(cryptodotcom_provider)
        self.mapper_manager.register_mapper(CryptoDotComMarketDataMapper)

        self.market_data_manager.register_provider(cryptodotcom_provider)

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

    def _setup_trading_context(self):
        for asset in self.assets:
            name = asset.name
            exchange = asset.exchange
            ticker_symbol = asset.ticker_symbol
            opening_balance = float(input(f"Set opening balance for {name} - {ticker_symbol} at {exchange.value}"))
            self.trading_context_manager.register_trading_context(ticker_symbol, TradingContext(starting_balance=opening_balance))

    def startup(self):
        trading_engine = TradingEngine(
            self.assets, self.order_manager,
            self.market_data_manager, self.consensus_manager,
            self.trading_context_manager,
            self.activity_queue
        )
        trading_engine.init_application()

    def register_provider(self, provider: ExchangeProvider):
        self.order_manager.register_provider(provider)
        self.market_data_manager.register_provider(provider)

    def register_mapper(self, mapper: Mapper):
        self.mapper_manager.register_mapper(mapper)

    def register_strategy(self, strategy: TradingStrategy):
        self.consensus_manager.register_strategy(strategy)

    def shutdown(self):
        self.trading_context_manager.print_context()

    pass
