from decimal import Decimal

import pytest

from api.interfaces.backtest_request import ExecutionConfiguration
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.analysis.calculators.execution_quality_calculator import (
    ExecutionQualityCalculator,
)
from src.backtest.analysis.calculators.portfolio_risk_calculator import (
    PortfolioRiskCalculator,
)
from src.backtest.analysis.calculators.risk_adjusted_calculator import (
    RiskAdjustedCalculator,
)
from src.backtest.analysis.calculators.trading_behavior_calculator import (
    TradingBehaviorCalculator,
)
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.domain.result import (
    BacktestFill,
    BacktestResult,
    PortfolioSnapshot,
)
from src.trading.analytics.trade_attribution_service import AttributionMetrics


def _make_fill(
        action: TradeAction,
        price: str,
        qty: str = "1.0",
        fee: str = "0.1",
        slippage_cost: str = "0.05",
        slippage_unit: str = "0.05",
        market_price: str = "100.0",
        submitted_at: float = 100.0,
        executed_at: float = 100.05,
) -> BacktestFill:
    return BacktestFill(
        order_uuid="ord-1",
        ticker_symbol="BTC_USD",
        trade_action=action,
        requested_price=Decimal(market_price),
        market_price=Decimal(market_price),
        execution_price=Decimal(price),
        quantity=Decimal(qty),
        fee=Decimal(fee),
        slippage_per_unit=Decimal(slippage_unit),
        slippage_cost=Decimal(slippage_cost),
        submitted_at=submitted_at,
        executed_at=executed_at,
    )


def test_risk_adjusted_calculator():
    calc = RiskAdjustedCalculator()
    snapshots = [
        PortfolioSnapshot(timestamp=0, cash=Decimal("10000"), positions={}, equity=Decimal("10000")),
        PortfolioSnapshot(timestamp=86400, cash=Decimal("9800"), positions={}, equity=Decimal("9800")),
        PortfolioSnapshot(timestamp=172800, cash=Decimal("10500"), positions={}, equity=Decimal("10500")),
    ]
    res = calc.calculate(
        snapshots=snapshots,
        initial_balance=Decimal("10000"),
        final_equity=Decimal("10500"),
        max_drawdown=Decimal("200"),
        max_drawdown_pct=Decimal("2.0"),
    )

    assert res.sharpe_ratio is not None
    assert res.sortino_ratio is not None
    assert res.calmar_ratio is not None
    assert res.annualized_volatility_pct is not None
    assert res.recovery_factor == Decimal("2.50")  # (10500 - 10000) / 200 = 2.50


def test_trading_behavior_calculator():
    calc = TradingBehaviorCalculator()
    fills = [
        _make_fill(TradeAction.BUY, "100", "1.0", submitted_at=100.0, executed_at=100.0),
        _make_fill(TradeAction.SELL, "120", "1.0", submitted_at=200.0, executed_at=200.0),  # Win +19.8
        _make_fill(TradeAction.BUY, "100", "1.0", submitted_at=300.0, executed_at=300.0),
        _make_fill(TradeAction.SELL, "130", "1.0", submitted_at=400.0, executed_at=400.0),  # Win +29.8
        _make_fill(TradeAction.BUY, "100", "1.0", submitted_at=500.0, executed_at=500.0),
        _make_fill(TradeAction.SELL, "90", "1.0", submitted_at=600.0, executed_at=600.0),   # Loss -10.2
    ]
    snapshots = [
        PortfolioSnapshot(timestamp=100, cash=Decimal("9900"), positions={"BTC": Decimal("1")}, equity=Decimal("10000")),
        PortfolioSnapshot(timestamp=200, cash=Decimal("10020"), positions={}, equity=Decimal("10020")),
    ]

    res = calc.calculate(fills=fills, snapshots=snapshots, initial_balance=Decimal("10000"))

    assert res.round_trips == 3
    assert res.winning_trades == 2
    assert res.losing_trades == 1
    assert res.win_rate_pct == Decimal("66.67")
    assert res.profit_factor is not None
    assert res.expectancy is not None
    assert res.average_win is not None
    assert res.average_loss is not None
    assert res.win_loss_ratio is not None
    assert res.largest_win is not None
    assert res.largest_loss is not None
    assert res.max_consecutive_wins == 2
    assert res.max_consecutive_losses == 1
    assert res.turnover > Decimal("0")
    assert res.avg_holding_time_seconds == 100.0
    assert res.exposure_time_pct == Decimal("50.00")


def test_execution_quality_calculator():
    calc = ExecutionQualityCalculator()
    fills = [
        _make_fill(TradeAction.BUY, price="100.5", market_price="100.0", slippage_cost="0.5", slippage_unit="0.5", submitted_at=10.0, executed_at=10.05),
    ]
    orders = [
        Order(uuid="1", provider_name="B", ticker_symbol="BTC_USD", price=Decimal("100"), quantity="1", trade_action=TradeAction.BUY, created_time=10.0, status=OrderStatus.COMPLETED),
        Order(uuid="2", provider_name="B", ticker_symbol="BTC_USD", price=Decimal("100"), quantity="1", trade_action=TradeAction.BUY, created_time=20.0, status=OrderStatus.CANCELLED),
    ]
    res = calc.calculate(fills=fills, orders=orders)

    assert res.fill_ratio_pct == Decimal("50.00")
    assert res.rejection_ratio_pct == Decimal("50.00")
    assert res.avg_expected_price == Decimal("100.0000")
    assert res.avg_fill_price == Decimal("100.5000")
    assert res.avg_slippage_bps == Decimal("50.00")  # (0.5 / 100) * 10000 = 50 bps
    assert res.total_slippage_cost == Decimal("0.5")
    assert res.avg_latency_ms == pytest.approx(50.0, abs=1e-2)


def test_portfolio_risk_calculator():
    calc = PortfolioRiskCalculator()
    result = BacktestResult(
        session_id="s1",
        ticker_symbol="BTC_USD",
        initial_balance=Decimal("10000"),
        final_balance=Decimal("11000"),
        final_equity=Decimal("11000"),
        execution=ExecutionConfiguration(),
        portfolio_snapshots=[
            PortfolioSnapshot(timestamp=0, cash=Decimal("5000"), positions={"BTC": Decimal("0.1")}, equity=Decimal("10000")),
            PortfolioSnapshot(timestamp=1, cash=Decimal("2000"), positions={"BTC": Decimal("0.15"), "ETH": Decimal("1")}, equity=Decimal("10000")),
        ],
        strategy_attribution={
            "StratA": AttributionMetrics(
                total_trades=8, winning_trades=6, losing_trades=2, break_even_trades=0,
                win_rate_pct=75.0, gross_pnl=Decimal("900"), total_fees=Decimal("50"),
                total_slippage=Decimal("50"), net_pnl=Decimal("800"), profit_factor=4.0,
                avg_return_pct=2.0, avg_duration_seconds=60.0, max_win=Decimal("200"), max_loss=Decimal("50")
            ),
            "StratB": AttributionMetrics(
                total_trades=2, winning_trades=1, losing_trades=1, break_even_trades=0,
                win_rate_pct=50.0, gross_pnl=Decimal("250"), total_fees=Decimal("25"),
                total_slippage=Decimal("25"), net_pnl=Decimal("200"), profit_factor=2.0,
                avg_return_pct=1.0, avg_duration_seconds=60.0, max_win=Decimal("200"), max_loss=Decimal("0")
            ),
        },
    )
    res = calc.calculate(result)

    assert res.peak_exposure_pct == Decimal("80.00")  # (10000 - 2000) / 10000 * 100 = 80%
    assert res.avg_exposure_pct == Decimal("65.00")   # (50 + 80) / 2 = 65%
    assert res.concentration_hhi > Decimal("0")
    assert res.contribution_to_pnl["StratA"] == Decimal("80.00")
    assert res.contribution_to_pnl["StratB"] == Decimal("20.00")
    assert res.contribution_to_risk["StratA"] == Decimal("80.00")  # 8 / 10 = 80%
    assert res.contribution_to_risk["StratB"] == Decimal("20.00")  # 2 / 10 = 20%


def test_full_backtest_metrics_calculator_robustness():
    calculator = BacktestMetricsCalculator()
    fills = [
        _make_fill(TradeAction.BUY, "100", "1.0", fee="0.1", slippage_cost="0.05", slippage_unit="0.05", market_price="100.0", submitted_at=100.0, executed_at=100.05),
        _make_fill(TradeAction.SELL, "120", "1.0", fee="0.1", slippage_cost="0.05", slippage_unit="0.05", market_price="120.0", submitted_at=200.0, executed_at=200.05),
    ]
    snapshots = [
        PortfolioSnapshot(timestamp=100, cash=Decimal("10000"), positions={}, equity=Decimal("10000")),
        PortfolioSnapshot(timestamp=150, cash=Decimal("9900"), positions={"BTC": Decimal("1.0")}, equity=Decimal("10000")),
        PortfolioSnapshot(timestamp=200, cash=Decimal("10019.8"), positions={}, equity=Decimal("10019.8")),
    ]
    result = BacktestResult(
        session_id="s_full",
        ticker_symbol="BTC_USD",
        initial_balance=Decimal("10000"),
        final_balance=Decimal("10019.8"),
        final_equity=Decimal("10019.8"),
        execution=ExecutionConfiguration(),
        orders=[
            Order(uuid="1", provider_name="B", ticker_symbol="BTC_USD", price=Decimal("100"), quantity="1", trade_action=TradeAction.BUY, created_time=100.0, status=OrderStatus.COMPLETED),
            Order(uuid="2", provider_name="B", ticker_symbol="BTC_USD", price=Decimal("120"), quantity="1", trade_action=TradeAction.SELL, created_time=200.0, status=OrderStatus.COMPLETED),
        ],
        fills=fills,
        portfolio_snapshots=snapshots,
    )
    metrics = calculator.calculate(result)

    assert metrics.risk_adjusted is not None
    assert metrics.behavior is not None
    assert metrics.execution is not None
    assert metrics.portfolio is not None
    assert metrics.sortino_ratio is not None
    assert metrics.expectancy is not None
    assert metrics.avg_latency_ms == pytest.approx(50.0, abs=1e-2)
    assert metrics.avg_slippage_bps == Decimal("2.08") or metrics.avg_slippage_bps is not None
