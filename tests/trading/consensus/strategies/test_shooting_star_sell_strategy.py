from unittest.mock import MagicMock
import pytest
from api.interfaces.candle import Candle
from api.interfaces.trade_action import TradeAction
from src.trading.consensus.strategies.shooting_star_sell_strategy import ShootingStarSellStrategy


@pytest.fixture
def strategy():
    return ShootingStarSellStrategy()


def test_shooting_star_pattern_detected(strategy):
    # Body = abs(105 - 100) = 5
    # Upper Wick = 120 - 105 = 15 (>= 2 * 5 = 10)
    # Lower Wick = 100 - 99 = 1 (<= 0.5 * 5 = 2.5)
    candle = Candle(open='100', close='105', high='120', low='99', start_time=1000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is True


def test_shooting_star_pattern_not_detected_small_upper_wick(strategy):
    # Body = 5
    # Upper Wick = 107 - 105 = 2 (< 10)
    candle = Candle(open='100', close='105', high='107', low='99', start_time=1000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False


def test_shooting_star_pattern_not_detected_large_lower_wick(strategy):
    # Body = 5
    # Upper Wick = 120 - 105 = 15 (>= 10)
    # Lower Wick = 100 - 95 = 5 (> 2.5)
    candle = Candle(open='100', close='105', high='120', low='95', start_time=1000)

    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False


def test_empty_candles(strategy):
    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[]
    )
    assert result is False


def test_zero_body_candle(strategy):
    candle = Candle(open='100', close='100', high='110', low='95', start_time=1000)
    result = strategy.get_quorum(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC_USD",
        trading_context=MagicMock(),
        market_data=MagicMock(),
        candles=[candle]
    )
    assert result is False
