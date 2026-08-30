from __future__ import annotations

from dataclasses import field
from decimal import Decimal

from pydantic.dataclasses import dataclass

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from api.interfaces.backtest_request import ExecutionConfiguration


@dataclass(frozen=True)
class BacktestFill:
    order_uuid: str
    ticker_symbol: str
    trade_action: TradeAction
    requested_price: Decimal
    market_price: Decimal
    execution_price: Decimal
    quantity: Decimal
    fee: Decimal
    slippage_per_unit: Decimal
    slippage_cost: Decimal
    submitted_at: float
    executed_at: float


@dataclass(frozen=True)
class MarketDataPoint:
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    timestamp: int
    cash: Decimal
    positions: dict[str, Decimal]
    equity: Decimal


@dataclass
class BacktestResult:
    session_id: str
    asset: str
    initial_balance: Decimal
    final_balance: Decimal
    final_equity: Decimal
    execution: ExecutionConfiguration
    orders: list[Order] = field(default_factory=list)
    fills: list[BacktestFill] = field(default_factory=list)
    portfolio_snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    market_series: list[MarketDataPoint] = field(default_factory=list)
