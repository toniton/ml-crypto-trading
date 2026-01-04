from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BearishEngulfingSellStrategy(RuleBasedTradingStrategy):

    def __init__(self):
        super().__init__()
        self.type = TradeAction.SELL

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        if len(candles) < 2:
            return False

        latest = candles[-1]
        prev = candles[-2]

        try:
            latest_open = float(latest.open)
            latest_close = float(latest.close)
            prev_open = float(prev.open)
            prev_close = float(prev.close)
        except (ValueError, TypeError):
            return False

        # Previous candle must be bullish
        is_prev_bullish = prev_close > prev_open
        # Latest candle must be bearish
        is_latest_bearish = latest_close < latest_open

        if not is_prev_bullish or not is_latest_bearish:
            return False

        # Latest candle body must "engulf" the previous candle body
        # (Latest open >= Previous close) AND (Latest close <= Previous open)
        is_engulfing = latest_open >= prev_close and latest_close <= prev_open

        return is_engulfing
