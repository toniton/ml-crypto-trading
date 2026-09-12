from __future__ import annotations

from decimal import Decimal

from typing import Any, Optional

from pydantic.dataclasses import dataclass


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
    total_pnl: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    win_rate_pct: Optional[Decimal] = None
    profit_factor: Optional[Decimal] = None
    total_trades: Optional[int] = None
    total_orders: Optional[int] = None
    total_fills: Optional[int] = None
    equity_curve: Optional[list[dict[str, Any]]] = None


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
