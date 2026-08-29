from datetime import datetime, timezone
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from backtest.backtest_clock import BacktestClock
from backtest.backtest_data_loader import BacktestDataLoader
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_rest_service import BacktestRestService
from backtest.backtest_trading_scheduler import BacktestTradingScheduler
from backtest.backtest_websocket_service import BacktestWebSocketService
from backtest.events.domain_events import CandlesEvent, MarketDataEvent, TickEvent
from backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from backtest.execution.config import build_execution_model
from src.application import Application
from src.configuration.application_config import ApplicationConfig
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class BacktestEngine(ApplicationLoggingMixin):
    def __init__(
        self,
        app: Application,
        loader: BacktestDataLoader,
        clock: BacktestClock,
        scheduler: BacktestTradingScheduler,
        bus: BacktestEventBus,
        assets: list[Asset],
        config: Optional[ApplicationConfig] = None,
    ):
        self.config = config or ApplicationConfig()
        self.app = app
        self.bus = bus
        self.loader = loader
        self.clock = clock
        self.scheduler = scheduler
        self._assets = assets
        self._assets_map = {a.ticker_symbol: a for a in assets}

        execution_model = build_execution_model(self.config)
        self.execution_engine = BacktestExecutionEngine(
            clock=clock,
            loader=loader,
            bus=bus,
            execution_model=execution_model,
            assets=self._assets_map,
            initial_balance=self.config.backtest_initial_balance,
        )

        self.rest_service = BacktestRestService(
            self.clock, self.bus, self.loader, self.execution_engine
        )
        self.websocket_service = BacktestWebSocketService(self.bus)
        self._is_running = False

        self.app.register_client(self.rest_service, self.websocket_service)

    def run(self, assets: list[Asset]):
        self.app_logger.info(f"Starting simulation for {len(assets)} assets")
        self._is_running = True

        for asset in assets:
            if not self._is_running:
                break
            self._run_asset_loop(asset)

        if self.app:
            self.app.shutdown()
        self.app_logger.info("Simulation complete")
        self._is_running = False

    def _run_asset_loop(self, asset: Asset):
        try:
            self.clock.reset(asset.ticker_symbol)
            self.app_logger.info(
                f"Started backtest loop for {asset.ticker_symbol}"
            )

            while self._is_running and self.clock.tick(asset.ticker_symbol):
                timestamp = self.clock.now(asset.ticker_symbol)
                readable_datetime = datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                )
                self.app_logger.info(
                    f"Clock: {asset.ticker_symbol} @ {timestamp} or "
                    f"{readable_datetime}"
                )

                # Phase 1: MARKET DATA
                data_point = self.loader.get_data(asset.ticker_symbol, timestamp)
                if data_point:
                    market_data = MarketData(
                        close_price=data_point.close_price,
                        low_price=data_point.low_price,
                        high_price=data_point.high_price,
                        volume=data_point.volume,
                        timestamp=float(data_point.timestamp),
                    )
                    self.bus.publish(MarketDataEvent(
                        market_data=market_data,
                        ticker_symbol=asset.ticker_symbol,
                    ))
                    candle = Candle(
                        open=market_data.close_price,
                        high=market_data.high_price,
                        low=market_data.low_price,
                        close=market_data.close_price,
                        start_time=float(market_data.timestamp),
                    )
                    self.bus.publish(CandlesEvent(
                        ticker_symbol=asset.ticker_symbol,
                        candles=[candle],
                    ))

                # Phase 2: EXECUTION — fill due orders against this tick
                self.execution_engine.process(asset.ticker_symbol, timestamp)

                # Phase 3: STRATEGY — trading decisions
                self.scheduler.on_tick(timestamp, asset)

                # Phase 4: TICK COMPLETE
                self.bus.publish(TickEvent(timestamp=timestamp))

        except Exception as e:
            self.app_logger.error(
                f"Error in backtest loop for {asset.ticker_symbol}: {e}"
            )

    def stop(self):
        self._is_running = False
