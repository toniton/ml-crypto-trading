from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyActiveOpenPositionsCountStrategy(RuleBasedTradingStrategy):
    def __init__(self, open_position_threshold=15):
        super().__init__()
        self.open_position_threshold = open_position_threshold
        self.type = TradeAction.BUY

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.BUY:
            return False

        if len(trading_context.open_positions) < self.open_position_threshold:
            return True

        return False
