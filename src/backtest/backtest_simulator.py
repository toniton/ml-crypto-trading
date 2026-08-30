from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_data_loader import BacktestDataLoader, HistoricalDataPoint
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.domain.result import MarketDataPoint, PortfolioSnapshot
from src.backtest.events.domain_events import (
    CandlesEvent,
    MarketDataEvent,
    MarketDataPointEvent,
    PortfolioSnapshotEvent,
    TickEvent,
)
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine

StrategyCallback = Callable[[Asset, int, Optional[MarketData], list[Candle]], None]


class BacktestSimulator:
    def __init__(
            self,
            clock: BacktestClock,
            loader: BacktestDataLoader,
            execution_engine: BacktestExecutionEngine,
            bus: BacktestEventBus,
            strategy: Optional[StrategyCallback] = None,
    ):
        self._clock = clock
        self._loader = loader
        self._execution_engine = execution_engine
        self._bus = bus
        self._strategy = strategy
        self._candles: dict[str, list[Candle]] = {}
        self._is_running = True

    def run(self, assets: list[Asset]) -> None:
        for asset in assets:
            if not self._is_running:
                break
            self._clock.reset(asset.ticker_symbol)
            while self._is_running and self._clock.tick(asset.ticker_symbol):
                self.step(asset)

    def step(self, asset: Asset) -> None:
        symbol = asset.ticker_symbol
        timestamp = self._clock.now(symbol)
        data_point = self._loader.get_data(symbol, timestamp)
        market_data = self._to_market_data(data_point)
        candles = self._candles.setdefault(symbol, [])

        if market_data:
            candle = self._to_candle(data_point)
            candles.append(candle)
            self._bus.publish(MarketDataEvent(market_data=market_data, ticker_symbol=symbol))
            self._bus.publish(CandlesEvent(candles=[candle], ticker_symbol=symbol))
            self._bus.publish(
                MarketDataPointEvent(point=self._to_market_point(data_point), ticker_symbol=symbol)
            )

        self._execution_engine.process(symbol, timestamp)

        if self._strategy:
            self._strategy(asset, timestamp, market_data, candles)

        self._bus.publish(
            PortfolioSnapshotEvent(
                snapshot=self._snapshot(asset, timestamp, data_point), ticker_symbol=symbol
            )
        )
        self._bus.publish(TickEvent(tick_time=timestamp))

    def stop(self) -> None:
        self._is_running = False

    @staticmethod
    def _to_market_data(data_point: Optional[HistoricalDataPoint]) -> Optional[MarketData]:
        if data_point is None:
            return None
        return MarketData(
            close_price=data_point.close_price,
            low_price=data_point.low_price,
            high_price=data_point.high_price,
            volume=data_point.volume,
            timestamp=float(data_point.timestamp),
        )

    @staticmethod
    def _to_candle(data_point: HistoricalDataPoint) -> Candle:
        return Candle(
            open=data_point.open_price,
            high=data_point.high_price,
            low=data_point.low_price,
            close=data_point.close_price,
            start_time=float(data_point.timestamp),
        )

    @staticmethod
    def _to_market_point(data_point: HistoricalDataPoint) -> MarketDataPoint:
        return MarketDataPoint(
            timestamp=data_point.timestamp,
            open=data_point.open_price,
            high=data_point.high_price,
            low=data_point.low_price,
            close=data_point.close_price,
            volume=data_point.volume,
        )

    def _snapshot(
            self, asset: Asset, timestamp: int, data_point: Optional[HistoricalDataPoint]
    ) -> PortfolioSnapshot:
        cash = self._execution_engine.account.balance_usd
        positions = dict(self._execution_engine.account.positions)
        close = data_point.close_price if data_point else Decimal("0")
        position_value = positions.get(asset.ticker_symbol, Decimal("0")) * close
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=cash,
            positions=positions,
            equity=cash + position_value,
        )
