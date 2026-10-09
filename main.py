import sys
import time

from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.llm_config import LlmConfig
from src.configuration.trading_config import TradingConfig


def _assert_python_version() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError(
            f"Rio Trading requires Python 3.11+, but running on {sys.version_info[0]}.{sys.version_info[1]}."
        )


def main():
    _assert_python_version()
    environment_config = EnvironmentConfig()

    application_config = ApplicationConfig()
    trading_config = TradingConfig(_yaml_file=application_config.trading_config_filepath)
    llm_config = LlmConfig()

    is_backtest_mode = application_config.backtest_mode is True
    app = Application(
        application_config=application_config, environment_config=environment_config,
        trading_config=trading_config, llm_config=llm_config,
        is_backtest_mode=is_backtest_mode,
    )
    app.startup()

    if is_backtest_mode:
        app.run_backtest()
        app.shutdown()
    else:
        try:
            while app.is_running.is_set():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            app.shutdown()


if __name__ == "__main__":
    main()
