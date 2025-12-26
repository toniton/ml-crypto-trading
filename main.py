#!/usr/bin/env python3
import logging
import threading

from backtest.backtest_application import BacktestApplication
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig


def main():
    logging.basicConfig(level=logging.INFO)
    environment_config = EnvironmentConfig()

    application_config = ApplicationConfig()
    assets_config = AssetsConfig(_yaml_file=application_config.assets_config_filepath)

    is_backtest_mode = application_config.backtest_mode or False
    if is_backtest_mode:
        runner = BacktestApplication(
            application_config=application_config, environment_config=environment_config,
            assets_config=assets_config, is_backtest_mode=is_backtest_mode)
        runner.startup()
    else:
        app = Application(application_config=application_config, environment_config=environment_config,
                          assets_config=assets_config)
        app_thread = threading.Thread(target=app.startup, name="TradingEngine")
        app_thread.start()


if __name__ == "__main__":
    main()
