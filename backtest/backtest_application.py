import threading
from time import sleep

from pydantic import SecretStr
from testcontainers.postgres import PostgresContainer

from backtest.backtest_clock import BacktestClock
from backtest.backtest_config import BacktestConfig
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
        backtest_config = BacktestConfig()
        loader = BacktestDataLoader(backtest_config.historical_data_path)
        # Load data first to get timestamps
        data_points = loader.load("btc-usd", use_mini=True)
        timestamps = [dp.timestamp for dp in data_points]

        clock = BacktestClock(timestamps=timestamps, tick_delay=backtest_config.backtest_tick_delay)
        scheduler = BacktestTradingScheduler(clock)

        with PostgresContainer("postgres:16") as postgres:
            psql_url = f"{postgres.get_container_host_ip()}:{postgres.get_exposed_port(postgres.port)}"
            application_config = self._application_config.model_copy(
                update={"database_connection_host": psql_url}
            )
            environment_config = self._environment_config.model_copy(
                update={
                    "postgres_user": postgres.username, "postgres_database":postgres.dbname,
                    "postgres_password": SecretStr(postgres.password)
                }
            )
            app = Application(
                application_config=application_config, environment_config=environment_config,
                assets_config=self._assets_config, is_backtest_mode=self._is_backtest_mode,
                trading_scheduler=scheduler
            )
            backtest_engine = BacktestEngine(app, loader, clock, scheduler, backtest_config)
            app_thread = threading.Thread(target=app.startup, name="BacktestApplication")
            app_thread.start()
            backtest_thread = threading.Thread(target=backtest_engine.run, name="BacktestEngine")
            backtest_thread.start()
            backtest_thread.join()
            app_thread.join()
            sleep(1)
