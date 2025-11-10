from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class SellStopLossStrategy(RuleBasedTradingStrategy):

    def __init__(self, stop_loss_pct: float = 0.02):
        super().__init__()
        self.type = TradeAction.SELL
        self.stop_loss_pct = stop_loss_pct

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        current_price = market_data.close_price
        open_orders = trading_context.open_positions

        for order in open_orders:
            loss_pct = (float(order.price) - float(current_price)) / float(order.price)
            if loss_pct >= self.stop_loss_pct:
                return True

        return False
