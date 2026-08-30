from __future__ import annotations

from decimal import Decimal

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
