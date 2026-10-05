from decimal import Decimal
from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trading_context import TradingContext
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.factories.trading_expression_factory import TradingExpressionFactory
from src.trading.regimes.market_regime import MarketRegime


def _sample_asset():
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=4,
        name="BTC_USD",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
    )


def _sample_market_data():
    return MarketData(
        volume=Decimal("1500"),
        high_price=Decimal("65000"),
        low_price=Decimal("64000"),
        close_price=Decimal("64500"),
        timestamp=1000.0,
        bid_price=Decimal("64490"),
        ask_price=Decimal("64510"),
    )


def _sample_account():
    return AccountBalance(
        currency="USD",
        available_balance=Decimal("10000"),
    )


def _sample_trading_context():
    return TradingContext(
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        starting_balance=Decimal("10000"),
        position_qty=Decimal("0.5"),
        avg_entry_price=Decimal("64000"),
    )


def _sample_candles(count=25):
    candles = []
    for i in range(count):
        price = 60000 + i * 200
        candles.append(
            Candle(
                open=Decimal(str(price - 50)),
                high=Decimal(str(price + 100)),
                low=Decimal(str(price - 100)),
                close=Decimal(str(price)),
                start_time=float(i * 60),
            )
        )
    return candles


def test_create_context_includes_regime_variables_and_constants():
    context = TradingExpressionFactory.create_context(
        asset=_sample_asset(),
        market_data=_sample_market_data(),
        account_balance=_sample_account(),
        trading_context=_sample_trading_context(),
        decision=None,
        candles=_sample_candles(),
    )

    regime = context.resolve_variable("regime")
    assert regime in [r.value for r in MarketRegime]
    assert context.resolve_variable("TRENDING_UP") == "TRENDING_UP"
    assert context.resolve_variable("RANGING") == "RANGING"
    assert context.resolve_variable("HIGH_VOLATILITY") == "HIGH_VOLATILITY"

    volatility = context.resolve_variable("volatility")
    assert isinstance(volatility, float)
    assert volatility >= 0.0

    trend_strength = context.resolve_variable("trend_strength")
    assert isinstance(trend_strength, float)

    spread = context.resolve_variable("spread")
    assert isinstance(spread, float)
    assert spread > 0.0


def test_create_strategy_context_includes_regime_variables():
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=_sample_trading_context(),
        market_data=_sample_market_data(),
        candles=_sample_candles(),
    )

    assert context.resolve_variable("regime") is not None
    assert context.resolve_variable("volatility") >= 0.0
    assert context.resolve_variable("liquidity") > 0.0


def test_functions_evaluate_regime_metrics():
    candles = _sample_candles(30)
    market_data = _sample_market_data()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=_sample_trading_context(),
        market_data=market_data,
        candles=candles,
    )

    regime_val = context.call_function("regime", [20])
    assert regime_val in [r.value for r in MarketRegime]

    vol_val = context.call_function("volatility", [20])
    assert isinstance(vol_val, float)

    trend_val = context.call_function("trend_strength", [20])
    assert isinstance(trend_val, float)

    liq_val = context.call_function("liquidity", [20])
    assert isinstance(liq_val, float)

    spread_val = context.call_function("spread", [])
    assert isinstance(spread_val, float)


def test_create_context_includes_portfolio_variables():
    from src.trading.protection.portfolio_policy_resolver import EffectivePortfolioConfig
    from src.trading.protection.quote_portfolio_guard import PortfolioRiskMetrics
    from src.configuration.portfolio_config import PortfolioExposureConfig, MarketRegimeConfig, QuotePortfolioGuardConfig
    from src.core.expressions.expression_parser import ExpressionParser

    risk_metrics = PortfolioRiskMetrics(
        total_equity=Decimal("20000"),
        total_cash=Decimal("15000"),
        reserved_cash=Decimal("1000"),
        available_cash=Decimal("14000"),
        invested_notional=Decimal("5000"),
        total_exposure_pct=Decimal("0.25"),
        asset_notional=Decimal("2000"),
        asset_concentration_pct=Decimal("0.10"),
        peak_equity=Decimal("20000"),
        drawdown_pct=Decimal("0.0"),
        daily_loss_pct=Decimal("0.0"),
        open_position_count=2,
    )
    effective_config = EffectivePortfolioConfig(
        exposure=PortfolioExposureConfig(max_total=Decimal("0.80"), max_per_asset=Decimal("0.25")),
        regime=MarketRegimeConfig(enabled=True),
        guard=QuotePortfolioGuardConfig(enabled=True, min_quote_reserve=Decimal("0.10")),
        regime_multiplier=Decimal("0.50"),
    )

    context = TradingExpressionFactory.create_context(
        asset=_sample_asset(),
        market_data=_sample_market_data(),
        account_balance=_sample_account(),
        trading_context=_sample_trading_context(),
        decision=None,
        candles=_sample_candles(),
        risk_metrics=risk_metrics,
        effective_config=effective_config,
    )

    assert context.resolve_variable("portfolio_equity") == 20000.0
    assert context.resolve_variable("portfolio_exposure") == 0.25
    assert context.resolve_variable("portfolio_open_positions") == 2
    assert context.resolve_variable("max_exposure") == 0.40  # 0.80 * 0.50 regime_multiplier
    assert context.resolve_variable("max_asset_exposure") == 0.125  # 0.25 * 0.50

    # Test formula evaluating regime and max_exposure
    parser = ExpressionParser("equity * (0.10 if regime == 'HIGH_VOLATILITY' else 0.20) / close")
    res = parser.parse(context)
    assert res is not None
    assert res > 0

