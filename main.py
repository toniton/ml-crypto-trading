#!/usr/bin/env python3
from kafka import KafkaProducer, KafkaConsumer
from sqlalchemy.orm import Session

from configuration.application_config import ApplicationConfig
from configuration.assets_config import AssetsConfig
from configuration.environment_config import EnvironmentConfig
from dao.database_setup import DatabaseSetup
from prediction.prediction_engine import PredictionEngine
from trading.consensus.consensus_manager import ConsensusManager
from trading.consensus.strategies.buy_strategies.false_buy_strategy import FalseBuyStrategy
from trading.consensus.strategies.buy_strategies.prediction_buy_strategy import PredictionBuyStrategy
from trading.consensus.strategies.sell_strategies.false_sell_strategy import FalseSellStrategy
from trading.consensus.strategies.sell_strategies.prediction_sell_strategy import PredictionSellStrategy
from trading.context.trading_context import TradingContext
from trading.context.trading_context_manager import TradingContextManager
from trading.mappers.cryptodotcom_marketdata_mapper import CryptoDotComMarketDataMapper
from trading.mappers.mapper_manager import MapperManager
from trading.markets.market_data_manager import MarketDataManager
from trading.orders.order_manager import OrderManager
from trading.providers.cryptodotcom_provider import CryptoDotComProvider
from trading.trading_engine import TradingEngine
from trading.unit_of_work import UnitOfWork


def main():
    environment_config = EnvironmentConfig()
    application_config = ApplicationConfig(
        _env_file=ApplicationConfig.get_env_path(environment_config.app_env)
    )

    database_setup = DatabaseSetup(environment_config, application_config)
    database_setup.create_tables()
    database_engine = database_setup.create_engine()
    database_session = Session(database_engine)

    unit_of_work = UnitOfWork(database_session)

    print(["Crypto Dot Com API Key", environment_config.crypto_dot_com_exchange_api_key])
    print(["Application config", application_config.crypto_dot_com_exchange_rest_endpoint])
    print(["Application config", application_config.crypto_dot_com_exchange_websocket_endpoint])

    cryptodotcom_provider = CryptoDotComProvider(
        application_config.crypto_dot_com_exchange_rest_endpoint,
        application_config.crypto_dot_com_exchange_websocket_endpoint,
        environment_config.crypto_dot_com_exchange_api_key,
        environment_config.crypto_dot_com_exchange_secret_key
    )

    assets_config = AssetsConfig()
    assets = assets_config.assets

    kafka_configuration = application_config.kafka_configuration
    producer = KafkaProducer(
        value_serializer=lambda v: v.encode('ascii'),
        bootstrap_servers=kafka_configuration.bootstrap_servers
    )
    consumer = KafkaConsumer(
        OrderManager.KAFKA_TOPIC,
        bootstrap_servers=kafka_configuration.bootstrap_servers
    )

    order_manager = OrderManager(unit_of_work)
    order_manager.register_provider(cryptodotcom_provider)

    mapper_manager = MapperManager()
    mapper_manager.register_mapper(cryptodotcom_provider.get_provider_name(), CryptoDotComMarketDataMapper)

    market_data_manager = MarketDataManager(assets)
    market_data_manager.register_provider(cryptodotcom_provider)
    market_data_manager.set_mapper_manager(mapper_manager)

    prediction_engine = PredictionEngine(assets)
    prediction_engine.load_assets_model()

    prediction_buy_strategy = PredictionBuyStrategy(prediction_engine)
    prediction_sell_strategy = PredictionSellStrategy(prediction_engine)
    false_buy_strategy = FalseBuyStrategy()
    false_sell_strategy = FalseSellStrategy()

    consensus_manager = ConsensusManager()
    consensus_manager.register_strategy(prediction_buy_strategy)
    consensus_manager.register_strategy(false_buy_strategy)
    consensus_manager.register_strategy(prediction_sell_strategy)
    consensus_manager.register_strategy(false_sell_strategy)

    trading_context_manager = TradingContextManager()
    for asset in assets:
        name = asset.name
        exchange = asset.exchange
        ticker_symbol = asset.ticker_symbol
        opening_balance = input(f"Set opening balance for {name} - {ticker_symbol} at {exchange.value}")
        trading_context_manager.register_trading_context(ticker_symbol, TradingContext(float(opening_balance)))

    trading_engine = TradingEngine(
        assets, consumer, producer, order_manager,
        market_data_manager, consensus_manager,
        trading_context_manager
    )
    trading_engine.init_application()
    pass


if __name__ == "__main__":
    main()
