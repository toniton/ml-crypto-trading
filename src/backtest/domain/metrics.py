from __future__ import annotations

from dataclasses import field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class RiskAdjustedMetrics:
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    calmar_ratio: Optional[Decimal] = None
    annualized_volatility_pct: Optional[Decimal] = None
    downside_deviation_pct: Optional[Decimal] = None
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    recovery_factor: Optional[Decimal] = None


@dataclass(frozen=True)
class TradingBehaviorMetrics:
    profit_factor: Optional[Decimal] = None
    expectancy: Optional[Decimal] = None
    expectancy_ratio: Optional[Decimal] = None
    win_rate_pct: Optional[Decimal] = None
    win_loss_ratio: Optional[Decimal] = None
    average_win: Optional[Decimal] = None
    average_loss: Optional[Decimal] = None
    largest_win: Optional[Decimal] = None
    largest_loss: Optional[Decimal] = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    turnover: Decimal = Decimal("0")
    avg_holding_time_seconds: float = 0.0
    exposure_time_pct: Decimal = Decimal("0")
    round_trips: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


@dataclass(frozen=True)
class ExecutionQualityMetrics:
    avg_expected_price: Optional[Decimal] = None
    avg_fill_price: Optional[Decimal] = None
    avg_slippage_bps: Optional[Decimal] = None
    avg_slippage_per_unit: Optional[Decimal] = None
    total_slippage_cost: Decimal = Decimal("0")
    avg_spread_bps: Optional[Decimal] = None
    avg_latency_ms: float = 0.0
    fill_ratio_pct: Decimal = Decimal("0")
    rejection_ratio_pct: Decimal = Decimal("0")


@dataclass(frozen=True)
class PortfolioRiskMetrics:
    peak_exposure_pct: Decimal = Decimal("0")
    avg_exposure_pct: Decimal = Decimal("0")
    concentration_hhi: Decimal = Decimal("0")
    contribution_to_pnl: dict[str, Decimal] = field(default_factory=dict)
    contribution_to_risk: dict[str, Decimal] = field(default_factory=dict)
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class BacktestMetrics:
    initial_balance: Decimal
    final_equity: Decimal
    absolute_pnl: Decimal
    percentage_return: Decimal
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    orders_submitted: int
    orders_filled: int
    orders_cancelled: int
    buy_count: int
    sell_count: int
    round_trips: int
    total_fees: Decimal
    total_slippage_cost: Decimal
    risk_adjusted: Optional[RiskAdjustedMetrics] = None
    behavior: Optional[TradingBehaviorMetrics] = None
    execution: Optional[ExecutionQualityMetrics] = None
    portfolio: Optional[PortfolioRiskMetrics] = None
    total_pnl: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    calmar_ratio: Optional[Decimal] = None
    annualized_volatility_pct: Optional[Decimal] = None
    recovery_factor: Optional[Decimal] = None
    win_rate_pct: Optional[Decimal] = None
    profit_factor: Optional[Decimal] = None
    expectancy: Optional[Decimal] = None
    avg_latency_ms: Optional[float] = None
    avg_slippage_bps: Optional[Decimal] = None
    total_trades: Optional[int] = None
    total_orders: Optional[int] = None
    total_fills: Optional[int] = None
    equity_curve: Optional[list[dict[str, Any]]] = None
    data_points: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass(frozen=True)
class BacktestSummary:
    session_id: str
    ticker_symbol: str
    status: str
    return_pct: Decimal
    absolute_pnl: Decimal
    max_drawdown_pct: Decimal
    round_trips: int
    orders_filled: int
    orders_cancelled: int
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    profit_factor: Optional[Decimal] = None
    win_rate_pct: Optional[Decimal] = None
    data_points: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
