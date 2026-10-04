from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api.interfaces.asset import Asset
from src.configuration.portfolio_config import (
    MarketRegimeConfig,
    PortfolioConfig,
    PortfolioExposureConfig,
    QuotePortfolioGuardConfig,
)


@dataclass(frozen=True)
class EffectivePortfolioConfig:
    exposure: PortfolioExposureConfig
    regime: MarketRegimeConfig
    guard: QuotePortfolioGuardConfig


class PortfolioPolicyResolver:
    @classmethod
    def resolve(cls, global_config: PortfolioConfig, asset: Asset) -> EffectivePortfolioConfig:
        override = asset.portfolio

        exposure = cls._resolve_exposure(global_config.exposure, override.exposure if override else None)
        regime = cls._resolve_regime(global_config.regime, override.regime if override else None)
        guard = cls._resolve_guard(global_config.guard, override.guard if override else None)

        return EffectivePortfolioConfig(exposure=exposure, regime=regime, guard=guard)

    @staticmethod
    def _resolve_exposure(
            global_exposure: PortfolioExposureConfig,
            override_exposure: Optional[PortfolioExposureConfig],
    ) -> PortfolioExposureConfig:
        if override_exposure is None:
            return global_exposure

        return PortfolioExposureConfig(
            max_total=(
                override_exposure.max_total
                if override_exposure.max_total is not None
                else global_exposure.max_total
            ),
            max_per_asset=(
                override_exposure.max_per_asset
                if override_exposure.max_per_asset is not None
                else global_exposure.max_per_asset
            ),
            max_per_quote=(
                override_exposure.max_per_quote
                if override_exposure.max_per_quote is not None
                else global_exposure.max_per_quote
            ),
        )

    @staticmethod
    def _resolve_regime(
            global_regime: MarketRegimeConfig,
            override_regime: Optional[MarketRegimeConfig],
    ) -> MarketRegimeConfig:
        if override_regime is None:
            return global_regime

        return MarketRegimeConfig(
            enabled=override_regime.enabled if override_regime.enabled is not None else global_regime.enabled,
            period=override_regime.period if override_regime.period is not None else global_regime.period,
            high_volatility_threshold=(
                override_regime.high_volatility_threshold
                if override_regime.high_volatility_threshold is not None
                else global_regime.high_volatility_threshold
            ),
            low_volatility_threshold=(
                override_regime.low_volatility_threshold
                if override_regime.low_volatility_threshold is not None
                else global_regime.low_volatility_threshold
            ),
            trend_threshold=(
                override_regime.trend_threshold
                if override_regime.trend_threshold is not None
                else global_regime.trend_threshold
            ),
            illiquid_spread_threshold=(
                override_regime.illiquid_spread_threshold
                if override_regime.illiquid_spread_threshold is not None
                else global_regime.illiquid_spread_threshold
            ),
            min_data_points=global_regime.min_data_points,
        )

    @staticmethod
    def _resolve_guard(
            global_guard: QuotePortfolioGuardConfig,
            override_guard: Optional[QuotePortfolioGuardConfig],
    ) -> QuotePortfolioGuardConfig:
        if override_guard is None:
            return global_guard

        return QuotePortfolioGuardConfig(
            enabled=override_guard.enabled if override_guard.enabled is not None else global_guard.enabled,
            max_drawdown=(
                override_guard.max_drawdown
                if override_guard.max_drawdown is not None
                else global_guard.max_drawdown
            ),
            max_daily_loss=(
                override_guard.max_daily_loss
                if override_guard.max_daily_loss is not None
                else global_guard.max_daily_loss
            ),
            max_position_count=(
                override_guard.max_position_count
                if override_guard.max_position_count is not None
                else global_guard.max_position_count
            ),
            min_quote_reserve=(
                override_guard.min_quote_reserve
                if override_guard.min_quote_reserve is not None
                else global_guard.min_quote_reserve
            ),
            max_quote_exposure=(
                override_guard.max_quote_exposure
                if override_guard.max_quote_exposure is not None
                else global_guard.max_quote_exposure
            ),
        )
