from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyRebalanceStrategy(RuleBasedTradingStrategy):
    def __init__(self, rebalance_threshold=0.01):
        super().__init__()
        self.rebalance_threshold = rebalance_threshold  # e.g. 1%
        self.type = TradeAction.BUY

    def get_quorum(self, _trade_action, _ticker_symbol, trading_context, _market_data, _candles):
        # if trading_context.closing_balance / trading_context.starting_balance > self.rebalance_threshold:
        if trading_context.closing_balance > (trading_context.starting_balance * self.rebalance_threshold):
            # Reinvest some profit if profit > 1%
            return True
        return False
