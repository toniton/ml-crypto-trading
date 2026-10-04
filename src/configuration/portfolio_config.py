from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PortfolioExposureConfig(BaseModel):
    max_total: Optional[Decimal] = Field(
        default=Decimal("0.80"),
        ge=0,
        le=1,
        description="Maximum total portfolio exposure fraction across all assets.",
        json_schema_extra={"mutable": True},
    )
    max_per_asset: Optional[Decimal] = Field(
        default=Decimal("0.25"),
        ge=0,
        le=1,
        description="Maximum exposure fraction allocated to any single asset.",
        json_schema_extra={"mutable": True},
    )
    max_per_quote: Optional[Decimal] = Field(
        default=Decimal("0.50"),
        ge=0,
        le=1,
        description="Maximum exposure fraction per quote currency.",
        json_schema_extra={"mutable": True},
    )


class MarketRegimeConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether market regime detection is enabled.",
        json_schema_extra={"mutable": True},
    )
    period: int = Field(
        default=20,
        ge=2,
        le=500,
        description="Number of candle observations for regime metrics.",
        json_schema_extra={"mutable": True},
    )
    high_volatility_threshold: Decimal = Field(
        default=Decimal("0.03"),
        gt=0,
        description="Threshold above which volatility is classified as high.",
        json_schema_extra={"mutable": True},
    )
    low_volatility_threshold: Decimal = Field(
        default=Decimal("0.005"),
        ge=0,
        description="Threshold below which volatility is classified as low.",
        json_schema_extra={"mutable": True},
    )
    trend_threshold: Decimal = Field(
        default=Decimal("0.005"),
        ge=0,
        description="Threshold for classifying directional trend strength.",
        json_schema_extra={"mutable": True},
    )
    illiquid_spread_threshold: Decimal = Field(
        default=Decimal("0.05"),
        gt=0,
        description="Bid/ask spread threshold for illiquidity classification.",
        json_schema_extra={"mutable": True},
    )
    min_data_points: int = Field(
        default=3,
        ge=1,
        description="Minimum number of candle data points required for classification.",
        json_schema_extra={"mutable": True},
    )


class QuotePortfolioGuardConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether quote portfolio guard enforcement is active.",
        json_schema_extra={"mutable": True},
    )
    max_drawdown: Optional[Decimal] = Field(
        default=Decimal("0.10"),
        ge=0,
        le=1,
        description="Maximum allowed drawdown fraction before trading halts.",
        json_schema_extra={"mutable": True},
    )
    max_daily_loss: Optional[Decimal] = Field(
        default=Decimal("0.05"),
        ge=0,
        le=1,
        description="Maximum allowed daily loss fraction.",
        json_schema_extra={"mutable": True},
    )
    max_position_count: Optional[int] = Field(
        default=10,
        ge=1,
        description="Maximum number of simultaneous open positions.",
        json_schema_extra={"mutable": True},
    )
    min_quote_reserve: Decimal = Field(
        default=Decimal("0.10"),
        ge=0,
        le=1,
        description="Fraction of total equity reserved in quote cash.",
        json_schema_extra={"mutable": True},
    )
    max_quote_exposure: Decimal = Field(
        default=Decimal("0.80"),
        ge=0,
        le=1,
        description="Maximum total quote-denominated exposure.",
        json_schema_extra={"mutable": True},
    )


class PortfolioConfig(BaseModel):
    exposure: PortfolioExposureConfig = Field(
        default_factory=PortfolioExposureConfig,
        description="Portfolio exposure limits.",
        json_schema_extra={"mutable": True},
    )
    regime: MarketRegimeConfig = Field(
        default_factory=MarketRegimeConfig,
        description="Market regime detection configuration.",
        json_schema_extra={"mutable": True},
    )
    guard: QuotePortfolioGuardConfig = Field(
        default_factory=QuotePortfolioGuardConfig,
        description="Portfolio guard configuration.",
        json_schema_extra={"mutable": True},
    )


class AssetPortfolioOverride(BaseModel):
    exposure: Optional[PortfolioExposureConfig] = Field(
        default=None,
        description="Asset-level exposure overrides.",
        json_schema_extra={"mutable": True},
    )
    regime: Optional[MarketRegimeConfig] = Field(
        default=None,
        description="Asset-level regime overrides.",
        json_schema_extra={"mutable": True},
    )
    guard: Optional[QuotePortfolioGuardConfig] = Field(
        default=None,
        description="Asset-level guard overrides.",
        json_schema_extra={"mutable": True},
    )
