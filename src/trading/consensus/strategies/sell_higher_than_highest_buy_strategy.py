from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class SellHigherThanHighestBuyStrategy(RuleBasedTradingStrategy):
    def __init__(self, grid_spacing_pct=0.5):
        super().__init__()
        self.grid_spacing_pct = grid_spacing_pct / 100
        self.type = TradeAction.SELL

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.SELL:
            return False

        # Skip if no buys have been made yet
        if trading_context.highest_buy == float('-inf'):
            return False

        current_price = float(market_data.close_price)
        threshold_price = trading_context.highest_buy * (1 + self.grid_spacing_pct)

        if current_price > threshold_price:
            return True

        return False
