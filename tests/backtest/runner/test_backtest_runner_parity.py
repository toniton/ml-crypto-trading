from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.trade_action import TradeAction
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.database.noop_database_manager import NoopDatabaseManager
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.strategies.strategy_registry import StrategyRegistry

T0 = 1_700_000_000


def _ts_str(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _write_history(tmp_path: Path, ticker_symbol: str, rows: list[tuple[int, str]]) -> str:
    path = tmp_path / f"{ticker_symbol}.csv"
    path.write_text(
        "timestamp;open;high;low;close;volume\n"
        + "\n".join(
            f"{_ts_str(ts)};{close};{close};{close};{close};1000" for ts, close in rows
        )
    )
    return str(tmp_path)


def _make_asset(strategies=None) -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="BTC",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.1,
        quantity_decimals=3,
        schedule=0,
        candles_timeframe="MIN1",
        strategies=strategies,
        consensus=ConsensusFactor(buy=1.0, sell=1.0),
    )


def _make_request(tmp_path: Path) -> BacktestRequest:
    return BacktestRequest(
        ticker_symbol="BTC_USD",
        start_time=datetime.fromtimestamp(T0, tz=timezone.utc),
        end_time=datetime.fromtimestamp(T0 + 50000, tz=timezone.utc),
        data_source=BacktestDataSourceRequest(path=str(tmp_path)),
        execution=ExecutionConfiguration(
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate=Decimal("0.001"),
        ),
        initial_balance=Decimal("10000.0"),
    )


class TestBacktestRunnerParity:
    def test_backtest_produces_fills_and_matches_trades(self, tmp_path):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "90"), (T0 + 2000, "80")])
        strat = StrategyConfig(
            type=StrategyType.STATIC,
            class_name="BuyLowerThanLowestBuyStrategy",
            action=TradeAction.BUY,
        )
        asset = _make_asset(strategies=[strat])
        runner = BacktestRunner(
            db_manager=NoopDatabaseManager(),
            assets={"BTC_USD": asset},
            strategy_registry=StrategyRegistry(),
        )

        result = runner.run_one(_make_request(tmp_path))

        assert len(result.fills) == 2

    def test_backtest_session_id_starts_with_prefix(self, tmp_path):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "110")])
        asset = _make_asset(strategies=[])
        runner = BacktestRunner(
            db_manager=NoopDatabaseManager(),
            assets={"BTC_USD": asset},
            strategy_registry=StrategyRegistry(),
        )

        result = runner.run_one(_make_request(tmp_path))

        assert result.session_id.startswith("bt_")

    def test_backtest_preserves_initial_balance(self, tmp_path):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "110")])
        asset = _make_asset(strategies=[])
        runner = BacktestRunner(
            db_manager=NoopDatabaseManager(),
            assets={"BTC_USD": asset},
            strategy_registry=StrategyRegistry(),
        )

        result = runner.run_one(_make_request(tmp_path))

        assert result.initial_balance == Decimal("10000.0")
