from decimal import Decimal

from src.configuration.portfolio_config import (
    MarketRegimeConfig,
    PortfolioExposureConfig,
    QuotePortfolioGuardConfig,
)
from src.trading.protection.portfolio_policy_resolver import EffectivePortfolioConfig
from src.trading.protection.quote_portfolio_guard import (
    PortfolioRiskMetrics,
    QuotePortfolioGuard,
)
from src.trading.regimes.market_regime import MarketRegime


def _create_test_config(
    guard_enabled: bool = True,
    min_reserve: Decimal = Decimal("0.10"),
    max_quote_exposure: Decimal = Decimal("0.80"),
    max_per_asset: Decimal = Decimal("0.25"),
    max_total: Decimal = Decimal("0.80"),
    max_drawdown: Decimal = Decimal("0.10"),
    max_position_count: int = 10,
    regime_enabled: bool = True,
) -> EffectivePortfolioConfig:
    return EffectivePortfolioConfig(
        exposure=PortfolioExposureConfig(
            max_total=max_total,
            max_per_asset=max_per_asset,
            max_per_quote=Decimal("0.50"),
        ),
        regime=MarketRegimeConfig(enabled=regime_enabled),
        guard=QuotePortfolioGuardConfig(
            enabled=guard_enabled,
            min_quote_reserve=min_reserve,
            max_quote_exposure=max_quote_exposure,
            max_drawdown=max_drawdown,
            max_position_count=max_position_count,
        ),
    )


def _create_risk_metrics(
    total_equity: Decimal = Decimal("10000"),
    total_cash: Decimal = Decimal("5000"),
    reserved_cash: Decimal = Decimal("0"),
    invested_notional: Decimal = Decimal("5000"),
    asset_notional: Decimal = Decimal("1000"),
    drawdown_pct: Decimal = Decimal("0.0"),
    open_position_count: int = 2,
) -> PortfolioRiskMetrics:
    available_cash = total_cash - reserved_cash
    total_exposure = invested_notional / total_equity if total_equity > 0 else Decimal("0")
    asset_concentration = asset_notional / total_equity if total_equity > 0 else Decimal("0")
    return PortfolioRiskMetrics(
        total_equity=total_equity,
        total_cash=total_cash,
        reserved_cash=reserved_cash,
        available_cash=available_cash,
        invested_notional=invested_notional,
        total_exposure_pct=total_exposure,
        asset_notional=asset_notional,
        asset_concentration_pct=asset_concentration,
        peak_equity=total_equity,
        drawdown_pct=drawdown_pct,
        daily_loss_pct=Decimal("0"),
        open_position_count=open_position_count,
    )


def test_guard_allows_valid_trade():
    config = _create_test_config()
    risk = _create_risk_metrics()

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("500"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is True


def test_guard_rejects_trade_when_exceeding_available_cash():
    config = _create_test_config()
    risk = _create_risk_metrics(total_cash=Decimal("1000"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("1200"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_breaching_min_quote_reserve():
    config = _create_test_config(min_reserve=Decimal("0.20"))
    risk = _create_risk_metrics(total_equity=Decimal("10000"), total_cash=Decimal("2500"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("1000"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_exceeding_max_quote_exposure():
    config = _create_test_config(max_quote_exposure=Decimal("0.80"))
    risk = _create_risk_metrics(total_equity=Decimal("10000"), invested_notional=Decimal("7500"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("1000"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_exceeding_max_asset_concentration():
    config = _create_test_config(max_per_asset=Decimal("0.20"))
    risk = _create_risk_metrics(total_equity=Decimal("10000"), asset_notional=Decimal("1500"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("1000"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_when_drawdown_limit_exceeded():
    config = _create_test_config(max_drawdown=Decimal("0.10"))
    risk = _create_risk_metrics(drawdown_pct=Decimal("-0.15"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("100"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_when_max_position_count_exceeded():
    config = _create_test_config(max_position_count=2)
    risk = _create_risk_metrics(asset_notional=Decimal("0"), open_position_count=2)

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="DOGE_USD",
        order_cost=Decimal("100"),
        risk=risk,
        regime=MarketRegime.RANGING,
        config=config,
    )

    assert decision.allowed is False


def test_guard_rejects_trade_under_illiquid_regime():
    config = _create_test_config(regime_enabled=True)
    risk = _create_risk_metrics()

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("100"),
        risk=risk,
        regime=MarketRegime.ILLIQUID,
        config=config,
    )

    assert decision.allowed is False


def test_guard_allows_trade_when_disabled():
    config = _create_test_config(guard_enabled=False)
    risk = _create_risk_metrics(drawdown_pct=Decimal("-0.50"))

    decision = QuotePortfolioGuard.evaluate(
        asset_symbol="CRO_USD",
        order_cost=Decimal("100"),
        risk=risk,
        regime=MarketRegime.ILLIQUID,
        config=config,
    )

    assert decision.allowed is True
