from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyLowerThanLowestBuyStrategy(RuleBasedTradingStrategy):
    def __init__(self, grid_spacing_pct=0.5):
        super().__init__()
        self.grid_spacing_pct = grid_spacing_pct / 100
        self.type = TradeAction.BUY

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.BUY:
            return False

        if trading_context.lowest_buy == float('inf'):
            return True

        current_price = float(market_data.close_price)
        if current_price < trading_context.lowest_buy * (1 - self.grid_spacing_pct):
            return True  # Buy at a lower price than the lowest buy

        return False
