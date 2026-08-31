from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.trade_action import TradeAction
from src.agent.backtest.backtest_service import BacktestService
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.database.database_manager import DatabaseManager
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.llm.tools.backtest_tool import BacktestTool
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.strategies.strategy_registry import StrategyRegistry

T0 = 1_700_000_000


@pytest.fixture
def db_manager():
    engine = create_engine("sqlite:///:memory:")
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory
    return db_mgr


def _make_asset(
        ticker_symbol: str = "BTC_USD",
        quote_decimals: int = 2,
        strategies: list[StrategyConfig] | None = None,
        consensus: ConsensusFactor | None = None,
) -> Asset:
    base, quote = ticker_symbol.split("_")
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=quote_decimals,
        name=base,
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.1,
        quantity_decimals=3,
        schedule=0,
        candles_timeframe="MIN1",
        strategies=strategies,
        consensus=consensus,
    )


def _buy_lower_strategy() -> StrategyConfig:
    return StrategyConfig(
        type=StrategyType.STATIC,
        class_name="BuyLowerThanLowestBuyStrategy",
        action=TradeAction.BUY,
    )


def _ts_str(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _write_history(tmp_path, ticker_symbol: str, rows: list[tuple[int, str]]) -> str:
    path = tmp_path / f"{ticker_symbol}.csv"
    path.write_text(
        "timestamp;open;high;low;close;volume\n"
        + "\n".join(
            f"{_ts_str(ts)};{close};{close};{close};{close};1000" for ts, close in rows
        )
    )
    return str(tmp_path)


def _make_request(tmp_path, ticker_symbol: str = "BTC_USD", **overrides) -> BacktestRequest:
    kwargs = {
        "ticker_symbol": ticker_symbol,
        "start_time": datetime.fromtimestamp(T0, tz=timezone.utc),
        "end_time": datetime.fromtimestamp(T0 + 2000, tz=timezone.utc),
        "data_source": BacktestDataSourceRequest(path=str(tmp_path)),
        "execution": ExecutionConfiguration(latency_ms=0.0, slippage_ticks=0, fee_rate=Decimal("0")),
    }
    kwargs.update(overrides)
    return BacktestRequest(**kwargs)


def _consensus() -> ConsensusFactor:
    return ConsensusFactor(buy=1.0, sell=1.0)


def _make_runner(db_manager, asset) -> BacktestRunner:
    return BacktestRunner(
        db_manager,
        {asset.ticker_symbol: asset},
        StrategyRegistry(),
    )


class TestBacktestRunner:
    def test_no_strategies_yields_no_fills(self, tmp_path, db_manager):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "101"), (T0 + 2000, "102")])
        asset = _make_asset(strategies=[], consensus=_consensus())
        runner = _make_runner(db_manager, asset)

        result = runner.run_one(_make_request(tmp_path))

        assert len(result.market_series) == 3
        assert len(result.portfolio_snapshots) == 3
        assert result.fills == []
        assert result.final_balance == Decimal("10000.0")
        assert result.final_equity == Decimal("10000.0")

    def test_unknown_asset_raises(self, tmp_path, db_manager):
        _write_history(tmp_path, "BTC_USD", [(T0, "100")])
        asset = _make_asset(strategies=[], consensus=_consensus())
        runner = _make_runner(db_manager, asset)

        with pytest.raises(ValueError):
            runner.run_one(_make_request(tmp_path, ticker_symbol="ETH_USD"))

    def test_time_range_filters_data(self, tmp_path, db_manager):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "101"), (T0 + 5000, "105")])
        asset = _make_asset(strategies=[], consensus=_consensus())
        runner = _make_runner(db_manager, asset)

        result = runner.run_one(
            _make_request(tmp_path, end_time=datetime.fromtimestamp(T0 + 1000, tz=timezone.utc))
        )

        assert [int(data.timestamp) for data in result.market_series] == [T0, T0 + 1000]


class TestBacktestRunnerFills:
    def test_static_buy_strategy_produces_fills(self, tmp_path, db_manager):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "99"), (T0 + 2000, "98")])
        asset = _make_asset(strategies=[_buy_lower_strategy()], consensus=_consensus())
        runner = _make_runner(db_manager, asset)

        result = runner.run_one(_make_request(tmp_path))

        assert [fill.execution_price for fill in result.fills] == [Decimal("100"), Decimal("99")]
        assert result.final_balance == Decimal("9980.10")


class TestBacktestTool:
    def test_run_backtest_returns_summary(self, tmp_path, db_manager):
        _write_history(tmp_path, "BTC_USD", [(T0, "100"), (T0 + 1000, "101")])
        asset = _make_asset(strategies=[], consensus=_consensus())
        runner = _make_runner(db_manager, asset)
        service = BacktestService(
            runner=runner,
            data_source_request=BacktestDataSourceRequest(path=str(tmp_path)),
            initial_balance=Decimal("10000.0"),
            execution=ExecutionConfiguration(latency_ms=0.0, slippage_ticks=0, fee_rate=Decimal("0")),
        )
        tool = BacktestTool(backtest_service=service)

        summary = tool._run("BTC_USD")

        assert "BTC_USD" in summary
        assert "session" in summary
        assert "Return: 0.0000%" in summary
        assert "Fills: 0" in summary
