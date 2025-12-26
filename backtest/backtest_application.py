import threading
from time import sleep

from backtest.backtest_clock import BacktestClock
from backtest.backtest_data_loader import BacktestDataLoader
from backtest.backtest_engine import BacktestEngine
from backtest.backtest_trading_scheduler import BacktestTradingScheduler
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import AssetsConfig
from src.configuration.environment_config import EnvironmentConfig


class BacktestApplication:
    def __init__(
            self, application_config: ApplicationConfig, environment_config: EnvironmentConfig,
            assets_config: AssetsConfig, is_backtest_mode: bool = False,
    ):
        self._application_config = application_config
        self._environment_config = environment_config
        self._assets_config = assets_config
        self._is_backtest_mode = is_backtest_mode

    def startup(self):
        loader = BacktestDataLoader(self._application_config.historical_data_path)
        data_points = loader.load("btc-usd", use_mini=True)
        timestamps = [dp.timestamp for dp in data_points]

        clock = BacktestClock(timestamps=timestamps, tick_delay=self._application_config.backtest_tick_delay)
        scheduler = BacktestTradingScheduler(clock)

        app = Application(application_config=self._application_config, environment_config=self._environment_config,
                          assets_config=self._assets_config, is_backtest_mode=self._is_backtest_mode,
                          backtest_scheduler=scheduler)
        backtest_engine = BacktestEngine(app, loader, clock, scheduler, self._application_config)
        app_thread = threading.Thread(target=app.startup, name="BacktestApplication")
        app_thread.start()
        backtest_thread = threading.Thread(target=backtest_engine.run, name="BacktestEngine")
        backtest_thread.start()
        backtest_thread.join()
        app_thread.join()
        sleep(1)
