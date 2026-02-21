import time

from backtest.backtest_application import BacktestApplication
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.trading_config import TradingConfig


def main():
    environment_config = EnvironmentConfig()

    application_config = ApplicationConfig()
    trading_config = TradingConfig(_yaml_file=application_config.trading_config_filepath)

    is_backtest_mode = application_config.backtest_mode is True
    if is_backtest_mode:
        runner = BacktestApplication(
            application_config=application_config, environment_config=environment_config,
            trading_config=trading_config, is_backtest_mode=is_backtest_mode)
        runner.startup()
    else:
        app = Application(application_config=application_config, environment_config=environment_config,
                          trading_config=trading_config)
        app.startup()
        try:
            while app.is_running.is_set():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            app.shutdown()


if __name__ == "__main__":
    main()
