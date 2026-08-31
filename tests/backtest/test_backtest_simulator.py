from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import BacktestRequest
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_simulator import BacktestSimulator
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.data.csv_backtest_data_source import CsvBacktestDataSource
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.fees.percentage_fee import PercentageFee
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.backtest.events.domain_events import (
    PortfolioSnapshotEvent,
    TickEvent,
)
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events import MarketDataEvent

T0 = 1_700_000_000


def _make_asset(ticker_symbol: str = "BTC_USD") -> Asset:
    base, quote = ticker_symbol.split("_")
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=base,
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.1,
        quantity_decimals=3,
        schedule=0,
        candles_timeframe="MIN1",
    )


def _ts_str(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _write_history(tmp_path, ticker_symbol: str, rows: list[tuple[int, str]]) -> None:
    path = tmp_path / f"{ticker_symbol}.csv"
    path.write_text(
        "timestamp;open;high;low;close;volume\n"
        + "\n".join(f"{_ts_str(ts)};{close};{close};{close};{close};1000" for ts, close in rows)
    )


def _make_engine(tmp_path, ticker_symbol: str = "BTC_USD") -> tuple[BacktestSimulator, BacktestEventBus, Asset]:
    rows = [(T0, "100"), (T0 + 1000, "101"), (T0 + 2000, "102")]
    _write_history(tmp_path, ticker_symbol, rows)

    asset = _make_asset(ticker_symbol)
    source = CsvBacktestDataSource(str(tmp_path))
    dataset = source.load(BacktestRequest(ticker_symbol=ticker_symbol))
    timestamps = list(dataset.timestamps)

    clock = BacktestClock({ticker_symbol: timestamps}, tick_delay=0.0)
    model = ExecutionModel(
        latency=FixedLatencyModel(0.0),
        slippage=FixedTickSlippage(0),
        fees=PercentageFee(Decimal("0")),
    )
    bus = BacktestEventBus()
    datasets = {ticker_symbol: dataset}
    execution_engine = BacktestExecutionEngine(
        clock=clock,
        datasets=datasets,
        bus=bus,
        execution_model=model,
        assets={ticker_symbol: asset},
        initial_balance=Decimal("10000.0"),
    )

    engine = BacktestSimulator(clock, datasets, execution_engine, bus, strategy=lambda *_: None)
    return engine, bus, asset


class TestBacktestSimulator:
    def test_run_emits_market_snapshot_and_tick_events(self, tmp_path):
        engine, bus, asset = _make_engine(tmp_path)
        market_data_points = []
        snapshots = []
        ticks = []
        bus.subscribe_callback(MarketDataEvent, lambda e: market_data_points.append(e.market_data))
        bus.subscribe_callback(PortfolioSnapshotEvent, lambda e: snapshots.append(e.snapshot))
        bus.subscribe_callback(TickEvent, lambda e: ticks.append(e.tick_time))

        engine.run([asset])

        assert len(market_data_points) == 3
        assert len(snapshots) == 3
        assert len(ticks) == 3
        assert [data.close_price for data in market_data_points] == [Decimal("100"), Decimal("101"), Decimal("102")]

    def test_step_emits_one_snapshot_per_tick(self, tmp_path):
        engine, bus, asset = _make_engine(tmp_path)
        snapshots = []
        bus.subscribe_callback(PortfolioSnapshotEvent, lambda e: snapshots.append(e.snapshot))

        engine.step(asset)
        engine.step(asset)

        assert len(snapshots) == 2
        assert snapshots[-1].equity == Decimal("10000.0")
