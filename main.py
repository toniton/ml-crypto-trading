#!/usr/bin/env python3
import os
import threading

from backtest.backtest_config import BacktestConfig
from backtest.backtest_application import BacktestApplication
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import AppEnvEnum, EnvironmentConfig
from src.configuration.helpers.application_helper import ApplicationHelper


def main():
    backtest_config = None
    is_backtest_mode = True if os.environ.get("BACKTEST_MODE") is not None else False
    environment_config = EnvironmentConfig()

    if is_backtest_mode:
        backtest_config = BacktestConfig()

    application_yaml = backtest_config.application_config_filepath if is_backtest_mode else (
        ApplicationHelper.get_application_config_path(AppEnvEnum.STAGING),
        ApplicationHelper.get_application_config_path(environment_config.app_env),
    )
    application_config = ApplicationConfig(_yaml_file=application_yaml)

    asset_yaml = backtest_config.assets_config_filepath if is_backtest_mode else ApplicationHelper.ASSETS_CONFIG_PATH
    assets_config = AssetsConfig(_yaml_file=asset_yaml)

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
