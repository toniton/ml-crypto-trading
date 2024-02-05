from entities.market_data import MarketData
from entities.trade_action import TradeAction
from trading.consensus.strategies.trading_strategy import TradingStrategy
from trading.context.trading_context import TradingContext


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
