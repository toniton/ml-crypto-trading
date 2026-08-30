from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.trade_action import TradeAction
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.domain.metrics import BacktestSummary
from src.backtest.domain.result import (
    BacktestFill,
    BacktestResult,
    PortfolioSnapshot,
)
from src.backtest.domain.session import BacktestSession


def _fill(action: TradeAction, price: str, quantity: str) -> BacktestFill:
    return BacktestFill(
        order_uuid="o",
        ticker_symbol="BTC_USD",
        trade_action=action,
        requested_price=Decimal(price),
        market_price=Decimal(price),
        execution_price=Decimal(price),
        quantity=Decimal(quantity),
        fee=Decimal("0"),
        slippage_per_unit=Decimal("0"),
        slippage_cost=Decimal("0"),
        submitted_at=0.0,
        executed_at=0.0,
    )


def _result(fills, equity: str) -> BacktestResult:
    return BacktestResult(
        session_id="bt_x",
        ticker_symbol="BTC_USD",
        initial_balance=Decimal("10000.0"),
        final_balance=Decimal(equity),
        final_equity=Decimal(equity),
        execution=ExecutionConfiguration(),
        orders=[],
        fills=fills,
        portfolio_snapshots=[
            PortfolioSnapshot(timestamp=0, cash=Decimal("10000.0"), positions={}, equity=Decimal("10000.0")),
            PortfolioSnapshot(timestamp=1, cash=Decimal("9500.0"), positions={}, equity=Decimal("9500.0")),
            PortfolioSnapshot(timestamp=2, cash=Decimal(equity), positions={}, equity=Decimal(equity)),
        ],
        market_series=[],
    )


def _session() -> BacktestSession:
    request = BacktestRequest(
        ticker_symbol="BTC_USD",
        start_time=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2023, 2, 1, tzinfo=timezone.utc),
        data_source=BacktestDataSourceRequest(path="/tmp"),
    )
    return BacktestSession(ticker_symbol="BTC_USD", request=request)


class TestBacktestMetricsCalculator:
    def test_calculates_performance_and_drawdown(self):
        result = _result([], equity="9800.0")
        metrics = BacktestMetricsCalculator().calculate(result)

        assert metrics.absolute_pnl == Decimal("-200.0")
        assert metrics.percentage_return == Decimal("-2")
        assert metrics.max_drawdown == Decimal("500.0")
        assert metrics.max_drawdown_pct == Decimal("5")
        assert metrics.orders_filled == 0

    def test_counts_fills_and_round_trips(self):
        fills = [
            _fill(TradeAction.BUY, "100", "1"),
            _fill(TradeAction.SELL, "110", "1"),
            _fill(TradeAction.BUY, "120", "0.5"),
        ]
        metrics = BacktestMetricsCalculator().calculate(_result(fills, equity="10000.0"))

        assert metrics.buy_count == 2
        assert metrics.sell_count == 1
        assert metrics.round_trips == 1

    def test_summary(self):
        session = _session()
        metrics = BacktestMetricsCalculator().calculate(_result([], equity="10000.0"))
        summary = BacktestMetricsCalculator().summarize(session, metrics)

        assert isinstance(summary, BacktestSummary)
        assert summary.session_id == session.id
        assert summary.ticker_symbol == "BTC_USD"
        assert summary.status == session.status.value
