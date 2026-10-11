from decimal import Decimal
import pytest

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.core.expressions.default_context import DefaultContext
from src.core.expressions.expression_parser import ExpressionParser
from src.core.expressions.rolling_window_evaluator import RollingWindowEvaluator
from src.trading.strategies.expression_strategy import ExpressionStrategy


def _make_candle(high=100.0, low=90.0, close=95.0, candle_open=92.0, volume=10.0, start_time=1.0) -> Candle:
    return Candle(
        open=Decimal(str(candle_open)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        start_time=float(start_time),
        volume=Decimal(str(volume)),
    )


def _make_market(close="106", high="110", low="95", timestamp=4.0) -> MarketData:
    return MarketData(
        volume=Decimal("1000"),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        timestamp=float(timestamp),
    )


def test_highest_and_lowest_calculation():
    candles = [
        _make_candle(high=100.0, low=95.0, start_time=1.0),
        _make_candle(high=105.0, low=98.0, start_time=2.0),
        _make_candle(high=103.0, low=94.0, start_time=3.0),
    ]
    evaluator = RollingWindowEvaluator(candles)

    assert evaluator.highest("high", 3) == 105.0
    assert evaluator.lowest("low", 3) == 94.0


def test_evaluator_supported_series():
    candles = [
        _make_candle(high=100.0, low=90.0, close=98.0, candle_open=91.0, volume=50.0, start_time=1.0),
        _make_candle(high=102.0, low=88.0, close=94.0, candle_open=99.0, volume=75.0, start_time=2.0),
    ]
    evaluator = RollingWindowEvaluator(candles)

    assert evaluator.highest("close", 2) == 98.0
    assert evaluator.lowest("open", 2) == 91.0
    assert evaluator.highest("volume", 2) == 75.0


def test_evaluator_insufficient_history_returns_none():
    candles = [
        _make_candle(high=100.0, start_time=1.0),
        _make_candle(high=105.0, start_time=2.0),
    ]
    evaluator = RollingWindowEvaluator(candles)

    assert evaluator.highest("high", 3) is None
    assert evaluator.lowest("low", 3) is None


def test_evaluator_invalid_period_raises_value_error():
    evaluator = RollingWindowEvaluator([])
    with pytest.raises(ValueError, match="positive integer"):
        evaluator.highest("high", 0)
    with pytest.raises(ValueError, match="positive integer"):
        evaluator.lowest("low", -5)


def test_evaluator_unsupported_series_raises_value_error():
    candles = [_make_candle(high=100.0, start_time=1.0)]
    evaluator = RollingWindowEvaluator(candles)
    with pytest.raises(ValueError, match="Unsupported series"):
        evaluator.highest("unsupported", 1)


def test_lookahead_bias_excludes_active_forming_candle():
    prior_candles = [
        _make_candle(high=100.0, low=90.0, close=95.0, start_time=1.0),
        _make_candle(high=105.0, low=92.0, close=99.0, start_time=2.0),
        _make_candle(high=103.0, low=91.0, close=97.0, start_time=3.0),
    ]
    active_forming_candle = _make_candle(
        high=110.0, low=95.0, close=106.0, start_time=4.0
    )
    all_candles = [*prior_candles, active_forming_candle]
    market_data = _make_market(close="106", high="110", low="95", timestamp=4.0)

    evaluator = RollingWindowEvaluator(all_candles, market_data)

    assert evaluator.highest("high", 3) == 105.0


def test_expression_breakout_evaluation():
    candles = [
        _make_candle(high=100.0, low=90.0, close=95.0, start_time=1.0),
        _make_candle(high=105.0, low=92.0, close=99.0, start_time=2.0),
        _make_candle(high=103.0, low=91.0, close=97.0, start_time=3.0),
    ]
    market_breakout = _make_market(close="106", high="106", low="95", timestamp=4.0)
    market_equal = _make_market(close="105", high="105", low="95", timestamp=4.0)
    market_below = _make_market(close="104", high="104", low="95", timestamp=4.0)

    parser = ExpressionParser("close > highest(high, 3)")

    context_breakout = DefaultContext(
        variables={"close": 106.0},
        functions={"highest": RollingWindowEvaluator(candles, market_breakout).highest},
    )
    context_equal = DefaultContext(
        variables={"close": 105.0},
        functions={"highest": RollingWindowEvaluator(candles, market_equal).highest},
    )
    context_below = DefaultContext(
        variables={"close": 104.0},
        functions={"highest": RollingWindowEvaluator(candles, market_below).highest},
    )

    assert parser.parse(context_breakout) is True
    assert parser.parse(context_equal) is False
    assert parser.parse(context_below) is False


def test_insufficient_history_comparison_evaluates_false():
    candles = [
        _make_candle(high=100.0, start_time=1.0),
    ]
    market_data = _make_market(close="106", timestamp=2.0)
    parser = ExpressionParser("close > highest(high, 3)")

    context = DefaultContext(
        variables={"close": 106.0},
        functions={"highest": RollingWindowEvaluator(candles, market_data).highest},
    )

    assert parser.parse(context) is False


def test_parser_validation_diagnostics():
    resp_valid = ExpressionParser.inspect_semantics("close > highest(high, 20)")
    assert resp_valid.is_valid is True
    assert "highest" in resp_valid.referenced_functions
    assert "high" in resp_valid.referenced_variables

    resp_invalid_series = ExpressionParser.inspect_semantics("close > highest(invalid_series, 20)")
    assert resp_invalid_series.is_valid is False
    assert any("valid series name" in d.message for d in resp_invalid_series.diagnostics)

    resp_invalid_period = ExpressionParser.inspect_semantics("close > highest(high, 0)")
    assert resp_invalid_period.is_valid is False
    assert any("greater than 0" in d.message for d in resp_invalid_period.diagnostics)


def test_expression_strategy_integration():
    strategy = ExpressionStrategy(
        StrategyConfig(
            name="BTC_Breakout",
            type=StrategyType.DYNAMIC,
            action=TradeAction.BUY,
            expression="close > highest(high, 3)",
        )
    )
    trading_context = TradingContext(
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        starting_balance=Decimal("1000"),
        position_qty=Decimal("0"),
        avg_entry_price=Decimal("0"),
    )
    prior_candles = [
        _make_candle(high=100.0, start_time=1.0),
        _make_candle(high=105.0, start_time=2.0),
        _make_candle(high=103.0, start_time=3.0),
    ]
    market_breakout = _make_market(close="106", high="110", low="95", timestamp=4.0)
    all_candles = [*prior_candles, _make_candle(high=110.0, close=106.0, start_time=4.0)]

    quorum = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=trading_context,
        market_data=market_breakout,
        candles=all_candles,
    )
    assert quorum is True
