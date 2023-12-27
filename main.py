#!/usr/bin/env python3
from kafka import KafkaProducer, KafkaConsumer

from configuration.application_config import ApplicationConfig
from configuration.assets_config import AssetsConfig
from configuration.environment_config import EnvironmentConfig
from trading.orders.order_manager import OrderManager
from trading.orders.providers.cryptodotcom_provider import CryptoDotComProvider
from trading.predictions.prediction_engine import PredictionEngine
from trading.trading_engine import TradingEngine


def main():
    environment_config = EnvironmentConfig()
    application_config = ApplicationConfig(
        _env_file=ApplicationConfig.get_env_path(environment_config.app_env)
    )
    print(["Crypto Dot Com API Key", environment_config.crypto_dot_com_exchange_api_key])
    print(["Application config", application_config.crypto_dot_com_exchange_api_endpoint])

    cryptodotcom_provider = CryptoDotComProvider(
        application_config.crypto_dot_com_exchange_api_endpoint,
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

    order_manager = OrderManager()
    order_manager.register_provider(cryptodotcom_provider)

    prediction_engine = PredictionEngine()
    trading_engine = TradingEngine(assets, consumer, producer, order_manager, prediction_engine)
    trading_engine.init_application()
    pass


if __name__ == "__main__":
    main()
