from decimal import Decimal

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.trading.strategies.expression_strategy import ExpressionStrategy


def _make_context(position_qty="1", avg_entry="90"):
    return TradingContext(
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        starting_balance=Decimal("1000"),
        position_qty=Decimal(position_qty),
        avg_entry_price=Decimal(avg_entry),
    )


def _make_market(close="100", high="105", low="95"):
    return MarketData(
        volume=Decimal("1000"),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        timestamp=0,
    )


def _make_strategy(expression, action=TradeAction.BUY):
    return ExpressionStrategy(
        StrategyConfig(
            name="Test",
            type=StrategyType.DYNAMIC,
            action=action,
            expression=expression,
        )
    )


def test_buy_strategy_votes_when_expression_true():
    strategy = _make_strategy("close > 50")

    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=_make_context(),
        market_data=_make_market(),
        candles=[],
    )
    assert result is True


def test_buy_strategy_votes_false_when_expression_false():
    strategy = _make_strategy("close < 50")

    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=_make_context(),
        market_data=_make_market(),
        candles=[],
    )
    assert result is False


def test_strategy_ignores_other_direction():
    strategy = _make_strategy("close > 50", action=TradeAction.SELL)

    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=_make_context(),
        market_data=_make_market(),
        candles=[],
    )
    assert result is False


def test_strategy_reads_position_variables():
    strategy = _make_strategy("pnl > 0")

    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=_make_context(),
        market_data=_make_market(),
        candles=[],
    )
    assert result is True


def test_strategy_supports_indicator_functions():
    strategy = _make_strategy("rsi(3) < 30")
    candles = [
        Candle(open="100", close=str(close), high="110", low="90", start_time=i)
        for i, close in enumerate([105, 104, 103, 102, 101, 100])
    ]

    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=_make_context(),
        market_data=_make_market(),
        candles=candles,
    )
    assert result is True