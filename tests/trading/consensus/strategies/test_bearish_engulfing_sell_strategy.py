from unittest.mock import MagicMock
import pytest
from api.interfaces.candle import Candle
from api.interfaces.trade_action import TradeAction
from src.trading.consensus.strategies.bearish_engulfing_sell_strategy import BearishEngulfingSellStrategy


@pytest.fixture
def strategy():
    return BearishEngulfingSellStrategy()


def test_bearish_engulfing_pattern_detected(strategy):
    # Prev: Bullish (100 -> 105)
    # Latest: Bearish (106 -> 99) - Engulfs prev body
    prev = Candle(open='100', close='105', high='107', low='99', start_time=1000)
    latest = Candle(open='106', close='99', high='108', low='98', start_time=2000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[prev, latest]
    )
    assert result is True


def test_bearish_engulfing_exact_match(strategy):
    # Prev: Bullish (100 -> 105)
    # Latest: Bearish (105 -> 100) - Exactly engulfs prev body
    prev = Candle(open='100', close='105', high='107', low='99', start_time=1000)
    latest = Candle(open='105', close='100', high='106', low='99', start_time=2000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[prev, latest]
    )
    assert result is True


def test_not_engulfing_latest_smaller(strategy):
    # Prev: Bullish (100 -> 105)
    # Latest: Bearish (104 -> 101) - Does NOT engulf
    prev = Candle(open='100', close='105', high='107', low='99', start_time=1000)
    latest = Candle(open='104', close='101', high='105', low='100', start_time=2000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[prev, latest]
    )
    assert result is False


def test_not_bearish_latest_bullish(strategy):
    # Prev: Bullish (100 -> 105)
    # Latest: Bullish (106 -> 110)
    prev = Candle(open='100', close='105', high='107', low='99', start_time=1000)
    latest = Candle(open='106', close='110', high='111', low='105', start_time=2000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[prev, latest]
    )
    assert result is False


def test_insufficient_candles(strategy):
    candle = Candle(open='100', close='105', high='107', low='99', start_time=1000)
    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False
