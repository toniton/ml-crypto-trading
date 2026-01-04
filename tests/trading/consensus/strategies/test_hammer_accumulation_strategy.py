from unittest.mock import MagicMock
import pytest
from api.interfaces.candle import Candle
from api.interfaces.trade_action import TradeAction
from src.trading.consensus.strategies.hammer_accumulation_strategy import HammerAccumulationStrategy


@pytest.fixture
def strategy():
    return HammerAccumulationStrategy()


def test_hammer_pattern_detected(strategy):
    # Body = abs(105 - 110) = 5
    # Lower Wick = 100 - 90 = 10 (>= 2 * 5 = 10)
    # Upper Wick = 111 - 110 = 1 (<= 0.5 * 5 = 2.5)
    candle = Candle(open='110', close='105', high='111', low='90', start_time=1000)
    
    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is True


def test_hammer_pattern_not_detected_small_lower_wick(strategy):
    # Body = 5
    # Lower Wick = 100 - 98 = 2 (< 10)
    candle = Candle(open='110', close='105', high='111', low='98', start_time=1000)
    
    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False


def test_hammer_pattern_not_detected_large_upper_wick(strategy):
    # Body = 5
    # Lower Wick = 10 (>= 10)
    # Upper Wick = 115 - 110 = 5 (> 2.5)
    candle = Candle(open='110', close='105', high='115', low='90', start_time=1000)
    
    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False


def test_empty_candles(strategy):
    result = strategy.get_quorum(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[]
    )
    assert result is False
