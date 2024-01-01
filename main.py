#!/usr/bin/env python3
from kafka import KafkaProducer, KafkaConsumer

from configuration.application_config import ApplicationConfig
from configuration.assets_config import AssetsConfig
from configuration.environment_config import EnvironmentConfig
# from prediction.models.coinmarketcap_model import CoinMarketCapModel
from prediction.prediction_engine import PredictionEngine
from trading.mappers.cryptodotcom_marketdata_mapper import CryptoDotComMarketDataMapper
from trading.mappers.mapper_manager import MapperManager
from trading.markets.market_data_manager import MarketDataManager
from trading.orders.order_manager import OrderManager
from trading.providers.cryptodotcom_provider import CryptoDotComProvider
from trading.trading_engine import TradingEngine


def main():
    environment_config = EnvironmentConfig()
    application_config = ApplicationConfig(
        _env_file=ApplicationConfig.get_env_path(environment_config.app_env)
    )
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

    # model = CoinMarketCapModel(assets[0])
    # model.train_model()

    kafka_configuration = application_config.kafka_configuration
    producer = KafkaProducer(
        value_serializer=lambda v: v.encode('ascii'),
        bootstrap_servers=kafka_configuration.bootstrap_servers
    )
    consumer = KafkaConsumer(
        OrderManager.KAFKA_TOPIC,
        bootstrap_servers=kafka_configuration.bootstrap_servers
    )

    order_manager = OrderManager()
    order_manager.register_provider(cryptodotcom_provider)

    mapper_manager = MapperManager()
    mapper_manager.register_mapper(cryptodotcom_provider.get_provider_name(), CryptoDotComMarketDataMapper)

    market_data_manager = MarketDataManager()
    market_data_manager.register_provider(cryptodotcom_provider)
    market_data_manager.set_mapper_manager(mapper_manager)

    prediction_engine = PredictionEngine()
    trading_engine = TradingEngine(assets, consumer, producer, order_manager, market_data_manager, prediction_engine)
    trading_engine.init_application()
    pass


if __name__ == "__main__":
    main()
