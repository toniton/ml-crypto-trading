from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from src.agent.configuration.models import MarkdownBlock


class PortfolioQueryIntent(BaseModel):
    quote_currency: Optional[str] = Field(
        default=None,
        description="Specific quote currency to analyze (e.g., 'USD', 'USDC'). None for all portfolios.",
    )
    exchange: Optional[str] = Field(
        default=None,
        description="Specific exchange to analyze (e.g., 'CRYPTO_DOT_COM', 'BINANCE'). None for all exchanges.",
    )
    target_asset: Optional[str] = Field(
        default=None,
        description="Specific asset ticker (e.g. 'BTC_USD') if the user requested a specific asset review.",
    )
    focus_areas: list[str] = Field(
        default_factory=list,
        description=(
            "Key focus areas of the inquiry (e.g., 'drawdown', 'cash_reserves', 'concentration', "
            "'equity_valuation', 'health_check', 'rebalancing')."
        ),
    )


class AssetAllocation(BaseModel):
    ticker_symbol: str
    quantity: Decimal
    mark_price: Decimal
    position_value: Decimal
    weight_pct: Decimal


class QuotePortfolioSnapshot(BaseModel):
    exchange: str
    quote_currency: str
    cash_balance: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    total_equity: Decimal
    peak_equity: Decimal
    current_drawdown_pct: Decimal
    max_drawdown_limit: Optional[Decimal] = None
    max_concentration_limit: Optional[Decimal] = None
    allocations: list[AssetAllocation] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)


class PortfolioAnalysisResult(BaseModel):
    snapshots: list[QuotePortfolioSnapshot] = Field(default_factory=list)
    total_equity_usd_equivalent: Optional[Decimal] = None
    overall_health: str = "HEALTHY"  # HEALTHY, WARNING, CRITICAL
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PortfolioInsightsPresentation(BaseModel):
    blocks: list[MarkdownBlock] = Field(default_factory=list)
