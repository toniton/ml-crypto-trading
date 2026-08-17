import threading
from time import sleep

from backtest.backtest_clock import BacktestClock
from backtest.backtest_data_loader import BacktestDataLoader
from backtest.backtest_engine import BacktestEngine
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_trading_scheduler import BacktestTradingScheduler
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.llm_config import LlmConfig
from src.configuration.trading_config import TradingConfig


class BacktestApplication:
    def __init__(
            self, application_config: ApplicationConfig, environment_config: EnvironmentConfig,
            trading_config: TradingConfig, llm_config: LlmConfig, is_backtest_mode: bool = False,
    ):
        self.app_thread = None
        self.app = None
        self.backtest_engine = None
        self.backtest_thread = None
        self._application_config = application_config
        self._environment_config = environment_config
        self._trading_config = trading_config
        self._llm_config = llm_config
        self._is_backtest_mode = is_backtest_mode
        self._timestamps = {}

    def startup(self):
        loader = BacktestDataLoader(self._application_config.historical_data_dir_path)
        for asset in self._trading_config.assets:
            data_points = loader.load(asset.ticker_symbol)
            self._timestamps[asset.ticker_symbol] = [dp.timestamp for dp in data_points]

        clock = BacktestClock(timestamps=self._timestamps, tick_delay=self._application_config.backtest_tick_delay)
        scheduler = BacktestTradingScheduler(clock)
        bus = BacktestEventBus()

        self.app = Application(application_config=self._application_config, environment_config=self._environment_config,
                               trading_config=self._trading_config, llm_config=self._llm_config,
                               is_backtest_mode=self._is_backtest_mode,
                               backtest_scheduler=scheduler)
        self.backtest_engine = BacktestEngine(self.app, loader, clock, scheduler, bus, self._application_config)
        self.app_thread = threading.Thread(target=self.app.startup, name="BacktestApplication", daemon=True)
        self.app_thread.start()
        if not self.app.is_ready.wait(timeout=10):
            raise RuntimeError("Application failed to start within 10 seconds")

        self.backtest_thread = threading.Thread(target=self.backtest_engine.run,
                                                name="BacktestEngine",
                                                args=(self._trading_config.assets,))
        self.backtest_thread.start()
        self.backtest_thread.join()
        if self.app_thread.is_alive():
            self.app_thread.join(timeout=2)
        sleep(1)

    def shutdown(self):
        if self.backtest_engine:
            self.backtest_engine.stop()
        if self.app:
            self.app.shutdown()
        if self.app_thread and self.app_thread.is_alive():
            self.app_thread.join(timeout=5)
