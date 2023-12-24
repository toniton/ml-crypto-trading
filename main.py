#!/usr/bin/env python3

from configuration.application_config import ApplicationConfig
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

    order_manager = OrderManager()
    order_manager.register_provider(cryptodotcom_provider)

    prediction_engine = PredictionEngine()
    trading_engine = TradingEngine(order_manager, prediction_engine)
    trading_engine.init_application()
    pass


if __name__ == "__main__":
    main()
