from decimal import Decimal
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.core.expressions.expression_parser import ExpressionParser
from src.trading.factories.trading_expression_factory import TradingExpressionFactory


def _sample_market_and_context():
    candles = [
        Candle(
            open=Decimal(str(100 + i)),
            high=Decimal(str(105 + i)),
            low=Decimal(str(95 + i)),
            close=Decimal(str(100 + i)),
            start_time=float(i * 60),
        )
        for i in range(25)
    ]
    market_data = MarketData(
        volume=Decimal("1000"),
        high_price=Decimal("125"),
        low_price=Decimal("115"),
        close_price=Decimal("124"),
        timestamp=1000.0,
        bid_price=Decimal("123.9"),
        ask_price=Decimal("124.1"),
    )
    trading_context = TradingContext(
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        starting_balance=Decimal("10000"),
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("110.0"),
    )
    return candles, market_data, trading_context


def test_regime_equality_with_string_literal():
    candles, market_data, trading_context = _sample_market_and_context()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=trading_context,
        market_data=market_data,
        candles=candles,
    )
    current_regime = context.resolve_variable("regime")

    expr = f'regime == "{current_regime}"'
    assert ExpressionParser(expr).parse(context) is True

    expr_false = 'regime == "NON_EXISTENT_REGIME"'
    assert ExpressionParser(expr_false).parse(context) is False


def test_regime_equality_with_constant_variable():
    candles, market_data, trading_context = _sample_market_and_context()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=trading_context,
        market_data=market_data,
        candles=candles,
    )
    current_regime = context.resolve_variable("regime")

    expr = f"regime == {current_regime}"
    assert ExpressionParser(expr).parse(context) is True


def test_regime_function_call_in_expression():
    candles, market_data, trading_context = _sample_market_and_context()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=trading_context,
        market_data=market_data,
        candles=candles,
    )
    current_regime = context.resolve_variable("regime")

    expr = f'regime(20) == "{current_regime}"'
    assert ExpressionParser(expr).parse(context) is True


def test_dynamic_quantity_sizing_with_regime_ternary():
    candles, market_data, trading_context = _sample_market_and_context()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=trading_context,
        market_data=market_data,
        candles=candles,
    )
    current_regime = context.resolve_variable("regime")

    expr = f"100.0 if regime == {current_regime} else 50.0"
    assert ExpressionParser(expr).parse(context) == 100.0

    expr_alt = "100.0 if regime == 'DIFFERENT_REGIME' else 50.0"
    assert ExpressionParser(expr_alt).parse(context) == 50.0


def test_volatility_and_spread_metrics_in_expression():
    candles, market_data, trading_context = _sample_market_and_context()
    context = TradingExpressionFactory.create_strategy_context(
        trading_context=trading_context,
        market_data=market_data,
        candles=candles,
    )

    expr = "volatility() >= 0.0 and spread() > 0.0 and liquidity() > 100"
    assert ExpressionParser(expr).parse(context) is True
