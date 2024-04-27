from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.trading.consensus.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class FalseBuyStrategy(RuleBasedTradingStrategy):

    def __init__(self):
        super().__init__()
        self.type = TradeAction.SELL

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData
    ):
        return True
        # return False
