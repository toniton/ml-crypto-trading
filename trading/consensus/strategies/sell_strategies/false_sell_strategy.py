from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_strategy import TradingStrategy
from api.interfaces.trading_context import TradingContext


class FalseSellStrategy(TradingStrategy):

    def __init__(self):
        super().__init__()
        self.type = TradeAction.SELL

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData
    ):
        return False
