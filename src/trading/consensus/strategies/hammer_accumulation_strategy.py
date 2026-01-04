from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class HammerAccumulationStrategy(RuleBasedTradingStrategy):

    def __init__(self):
        super().__init__()
        self.type = TradeAction.BUY

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        if not candles:
            return False

        latest_candle = candles[-1]
        try:
            open_price = float(latest_candle.open)
            close_price = float(latest_candle.close)
            high_price = float(latest_candle.high)
            low_price = float(latest_candle.low)
        except (ValueError, TypeError):
            return False

        body = abs(close_price - open_price)
        if body == 0:
            return False

        lower_wick = min(open_price, close_price) - low_price
        upper_wick = high_price - max(open_price, close_price)

        # Hammer pattern:
        # 1. Lower wick is at least 2x the body
        # 2. Upper wick is small (<= 0.5x the body)
        return lower_wick >= 2 * body and upper_wick <= 0.5 * body
