from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class DriftAttributionFactor(BaseModel):
    category: Literal["fees", "price_slippage", "fill_count", "quantity", "pnl"]
    label: str
    simulated_value: Optional[float] = None
    live_value: Optional[float] = None
    delta: Optional[float] = None
    unit: str = ""
    severity: Literal["ok", "warn", "drift"] = "ok"


class DriftEquityPoint(BaseModel):
    timestamp: str
    simulated_cumulative_pnl: float
    live_cumulative_pnl: float
    gap: float


class DriftSnapshotResponse(BaseModel):
    symbol: str
    venue: str = "default"
    quote_currency: str = "USD"
    commit_hash: Optional[str] = None
    snapshot_id: Optional[str] = None
    computed_at: str
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    drifted: bool = False
    simulated_fill_count: int = 0
    live_fill_count: int = 0
    fill_count_drift: int = 0
    simulated_quantity: float = 0.0
    live_quantity: float = 0.0
    quantity_drift: float = 0.0
    simulated_average_price: Optional[float] = None
    live_average_price: Optional[float] = None
    price_drift: Optional[float] = None
    simulated_fees: float = 0.0
    live_fees: float = 0.0
    fee_drift: float = 0.0
    simulated_pnl: Optional[float] = None
    live_pnl: Optional[float] = None
    pnl_gap: Optional[float] = None
    partial_fill_legs_merged: int = 0
    attribution_factors: list[DriftAttributionFactor] = Field(default_factory=list)
    equity_series: list[DriftEquityPoint] = Field(default_factory=list)
