from decimal import Decimal

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.portfolio_config import (
    MarketRegimeConfig,
    PortfolioConfig,
    PortfolioExposureConfig,
    QuotePortfolioGuardConfig,
)
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.protection.portfolio_policy_resolver import PortfolioPolicyResolver
from src.trading.protection.quote_portfolio_guard import PortfolioRiskMetrics, QuotePortfolioGuard
from src.trading.regimes.market_regime import MarketRegime
from src.trading.sizing.position_sizer import PositionSizer


def _create_asset(ticker: str = "BTC_USD") -> Asset:
    return Asset(
        base_ticker_symbol=ticker.split("_")[0],
        quote_ticker_symbol=ticker.split("_")[1],
        quote_decimals=2,
        name=ticker,
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
    )


def test_regime_exposure_multiplier_normal_vs_high_volatility():
    global_config = PortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.25")),
        regime=MarketRegimeConfig(enabled=True),
        guard=QuotePortfolioGuardConfig(enabled=True),
    )
    asset = _create_asset("BTC_USD")

    # Normal / Ranging regime
    normal_policy = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.RANGING)
    assert normal_policy.regime_multiplier == Decimal("1.0")
    assert normal_policy.effective_max_total == Decimal("0.80")
    assert normal_policy.effective_max_per_asset == Decimal("0.25")

    # High Volatility regime
    high_vol_policy = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.HIGH_VOLATILITY)
    assert high_vol_policy.regime_multiplier == Decimal("0.50")
    assert high_vol_policy.effective_max_total == Decimal("0.40")
    assert high_vol_policy.effective_max_per_asset == Decimal("0.125")

    # Illiquid regime
    illiquid_policy = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.ILLIQUID)
    assert illiquid_policy.regime_multiplier == Decimal("0.125")
    assert illiquid_policy.effective_max_total == Decimal("0.100")


def test_regime_scaled_position_sizing():
    formula = "equity * max_asset_exposure / close"
    sizer = PositionSizer(global_formula=formula)

    asset = _create_asset("BTC_USD")
    market = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("100"),
        low_price=Decimal("100"),
        close_price=Decimal("100"),
        timestamp=1000.0,
    )
    account = AccountBalance(currency="USD", available_balance=Decimal("10000"))
    trading_ctx = TradingContext(ticker_symbol="BTC_USD", exchange="BACKTEST", starting_balance=Decimal("10000"))
    decision = ConsensusDecision(TradeAction.BUY, "BTC_USD", {"s1": True}, {"s1": 1.0}, 1.0)

    global_config = PortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.20")),
        regime=MarketRegimeConfig(enabled=True),
    )

    # In NORMAL regime: max_asset_exposure = 20% -> 10000 * 0.20 / 100 = 20.0
    normal_config = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.NORMAL)
    qty_normal = sizer.calculate_quantity(
        asset=asset,
        market_data=market,
        decision=decision,
        account_balance=account,
        trading_context=trading_ctx,
        candles=[],
        effective_config=normal_config,
    )
    assert qty_normal == Decimal("20.0")

    # In HIGH_VOLATILITY regime: max_asset_exposure = 20% * 0.5 = 10% -> 10000 * 0.10 / 100 = 10.0
    high_vol_config = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.HIGH_VOLATILITY)
    qty_high_vol = sizer.calculate_quantity(
        asset=asset,
        market_data=market,
        decision=decision,
        account_balance=account,
        trading_context=trading_ctx,
        candles=[],
        effective_config=high_vol_config,
    )
    assert qty_high_vol == Decimal("10.0")


def test_quote_guard_blocks_when_regime_scaled_exposure_exceeded():
    global_config = PortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.25")),
        regime=MarketRegimeConfig(enabled=True),
        guard=QuotePortfolioGuardConfig(enabled=True, min_quote_reserve=Decimal("0.05")),
    )
    asset = _create_asset("BTC_USD")

    # $10,000 total equity, $2,000 currently invested in BTC (20% concentration)
    risk = PortfolioRiskMetrics(
        total_equity=Decimal("10000"),
        total_cash=Decimal("8000"),
        reserved_cash=Decimal("0"),
        available_cash=Decimal("8000"),
        invested_notional=Decimal("2000"),
        total_exposure_pct=Decimal("0.20"),
        asset_notional=Decimal("2000"),
        asset_concentration_pct=Decimal("0.20"),
        peak_equity=Decimal("10000"),
        drawdown_pct=Decimal("0.0"),
        daily_loss_pct=Decimal("0.0"),
        open_position_count=1,
    )

    # Proposed new BUY of $1,000 (total projected concentration = $3,000 / $10,000 = 30%)
    order_cost = Decimal("1000")

    # In NORMAL regime (max_per_asset = 25%), 30% exceeds 25%
    normal_config = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.RANGING)
    decision_normal = QuotePortfolioGuard.evaluate(
        asset_symbol="BTC_USD",
        order_cost=order_cost,
        risk=risk,
        regime=MarketRegime.RANGING,
        config=normal_config,
    )
    assert not decision_normal.allowed
    assert "Asset concentration limit exceeded" in decision_normal.reason

    # In HIGH_VOLATILITY regime (effective max_per_asset = 12.5%), already at 20%, definitely blocked
    high_vol_config = PortfolioPolicyResolver.resolve(global_config, asset, regime=MarketRegime.HIGH_VOLATILITY)
    decision_high_vol = QuotePortfolioGuard.evaluate(
        asset_symbol="BTC_USD",
        order_cost=Decimal("100"),  # even small $100 order -> 21% > 12.5%
        risk=risk,
        regime=MarketRegime.HIGH_VOLATILITY,
        config=high_vol_config,
    )
    assert not decision_high_vol.allowed
    assert "Asset concentration limit exceeded" in decision_high_vol.reason
