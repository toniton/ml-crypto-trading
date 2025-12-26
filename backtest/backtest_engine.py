import logging
from typing import Optional

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
        self.app.register_client(self.rest_client, self.websocket_client)

    def get_rest_client(self) -> BacktestExchangeRestClient:
        return self.rest_client

    def get_websocket_client(self) -> BacktestWebSocketClient:
        return self.websocket_client

    def run(self):
        logging.warning(f"BacktestEngine: Starting simulation with {self.clock.total_ticks} ticks")
        self.clock.reset()
        self._is_running = True

        tick_count = 0
        while self._is_running and self.clock.tick():
            tick_count += 1
            timestamp = self.clock.now()
            logging.warning(f"BacktestEngine: Clock tick: {tick_count}")

            data_point = self.loader.get_data(timestamp)
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
                    ticker_symbol="BTC_USD"
                ))

            self.scheduler.on_tick(timestamp)
            self.bus.publish(TickEvent(timestamp=timestamp))

        if self.app:
            self.app.shutdown()
        logging.warning("BacktestEngine: Simulation complete")
        self._is_running = False

    def stop(self):
        self._is_running = False
