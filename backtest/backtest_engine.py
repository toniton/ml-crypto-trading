import logging
import threading
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from backtest.backtest_clock import BacktestClock
from backtest.backtest_data_loader import BacktestDataLoader
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_exchange_rest_client import BacktestExchangeRestClient
from backtest.backtest_trading_scheduler import BacktestTradingScheduler
from backtest.backtest_websocket_client import BacktestWebSocketClient
from backtest.events import TickEvent, MarketDataEvent
from src.application import Application
from src.configuration.application_config import ApplicationConfig


class BacktestEngine:
    def __init__(
            self, app: Application, loader: BacktestDataLoader, clock: BacktestClock,
            scheduler: BacktestTradingScheduler, config: Optional[ApplicationConfig] = None
    ):
        self.config = config or ApplicationConfig()
        self.app = app
        self.bus = BacktestEventBus()
        self.loader = loader
        self.clock = clock
        self.scheduler = scheduler

        self.rest_client = BacktestExchangeRestClient(self.clock, self.bus, self.loader)
        self.websocket_client = BacktestWebSocketClient(self.bus)
        self._is_running = False
        self._threads = []
        self.app.register_client(self.rest_client, self.websocket_client)

    def run(self, assets: list[Asset]):
        logging.warning(f"BacktestEngine: Starting simulation for {len(assets)} assets")
        self._is_running = True
        self._threads = []

        for asset in assets:
            asset_thread = threading.Thread(target=self._run_asset_loop, args=(asset,), daemon=True)
            asset_thread.start()
            self._threads.append(asset_thread)

        for asset_thread in self._threads:
            asset_thread.join()

        if self.app:
            self.app.shutdown()
        logging.warning("BacktestEngine: Simulation complete")
        self._is_running = False

    def _run_asset_loop(self, asset: Asset):
        try:
            self.clock.reset(asset.ticker_symbol)
            logging.info(f"Started backtest loop for {asset.ticker_symbol}")

            while self._is_running and self.clock.tick(asset.ticker_symbol):
                timestamp = self.clock.now(asset.ticker_symbol)
                data_point = self.loader.get_data(asset.ticker_symbol, timestamp)

                if data_point:
                    market_data = MarketData(
                        close_price=str(data_point.close_price),
                        low_price=str(data_point.low_price),
                        high_price=str(data_point.high_price),
                        volume=str(data_point.volume),
                        timestamp=data_point.timestamp
                    )

                    self.bus.publish(MarketDataEvent(
                        market_data=market_data,
                        ticker_symbol=asset.ticker_symbol
                    ))

                self.scheduler.on_tick(timestamp, asset)
                self.bus.publish(TickEvent(timestamp=timestamp))
        except Exception as e:
            logging.error(f"Error in backtest loop for {asset.ticker_symbol}: {e}")

    def stop(self):
        self._is_running = False
