from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.configuration.portfolio_config import (
    AssetPortfolioOverride,
    MarketRegimeConfig,
    PortfolioConfig,
    PortfolioExposureConfig,
    QuotePortfolioGuardConfig,
)
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.protection.portfolio_policy_resolver import PortfolioPolicyResolver


def _create_test_asset(override: AssetPortfolioOverride | None = None) -> Asset:
    return Asset(
        base_ticker_symbol="CRO",
        quote_ticker_symbol="USD",
        quote_decimals=4,
        name="Cronos",
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=1.0,
        quantity_decimals=1,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        portfolio=override,
    )


def test_resolver_uses_global_defaults_when_no_asset_override():
    global_config = PortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.25")),
        regime=MarketRegimeConfig(period=20, high_volatility_threshold=Decimal("0.03")),
        guard=QuotePortfolioGuardConfig(min_quote_reserve=Decimal("0.10"), max_quote_exposure=Decimal("0.80")),
    )
    asset = _create_test_asset(override=None)

    effective = PortfolioPolicyResolver.resolve(global_config, asset)

    assert effective.exposure.max_per_asset == Decimal("0.25")
    assert effective.regime.period == 20
    assert effective.guard.min_quote_reserve == Decimal("0.10")


def test_resolver_applies_asset_exposure_override():
    global_config = PortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.25")),
    )
    asset = _create_test_asset(
        override=AssetPortfolioOverride(
            exposure=PortfolioExposureConfig(max_per_asset=Decimal("0.15"))
        )
    )

    effective = PortfolioPolicyResolver.resolve(global_config, asset)

    assert effective.exposure.max_per_asset == Decimal("0.15")


def test_resolver_applies_asset_regime_override():
    global_config = PortfolioConfig(
        regime=MarketRegimeConfig(high_volatility_threshold=Decimal("0.03")),
    )
    asset = _create_test_asset(
        override=AssetPortfolioOverride(
            regime=MarketRegimeConfig(high_volatility_threshold=Decimal("0.04"))
        )
    )

    effective = PortfolioPolicyResolver.resolve(global_config, asset)

    assert effective.regime.high_volatility_threshold == Decimal("0.04")


def test_resolver_applies_asset_guard_override():
    global_config = PortfolioConfig(
        guard=QuotePortfolioGuardConfig(min_quote_reserve=Decimal("0.10")),
    )
    asset = _create_test_asset(
        override=AssetPortfolioOverride(
            guard=QuotePortfolioGuardConfig(min_quote_reserve=Decimal("0.15"))
        )
    )

    effective = PortfolioPolicyResolver.resolve(global_config, asset)

    assert effective.guard.min_quote_reserve == Decimal("0.15")


def test_resolver_preserves_non_overridden_fields_in_override_block():
    global_config = PortfolioConfig(
        guard=QuotePortfolioGuardConfig(
            min_quote_reserve=Decimal("0.10"),
            max_quote_exposure=Decimal("0.80"),
            max_drawdown=Decimal("0.12"),
        )
    )
    asset = _create_test_asset(
        override=AssetPortfolioOverride(
            guard=QuotePortfolioGuardConfig(min_quote_reserve=Decimal("0.20"), max_drawdown=None)
        )
    )

    effective = PortfolioPolicyResolver.resolve(global_config, asset)

    assert effective.guard.min_quote_reserve == Decimal("0.20")
    assert effective.guard.max_quote_exposure == Decimal("0.80")
