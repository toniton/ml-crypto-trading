from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyContextAwareGridStrategy(RuleBasedTradingStrategy):
    def __init__(self, grid_drop_pct=0.5, cooldown_seconds=60):
        super().__init__()
        self.grid_drop_pct = grid_drop_pct / 100  # e.g. 0.5%
        self.cooldown_seconds = cooldown_seconds
        self.type = TradeAction.BUY

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.BUY:
            return False

        # Check grid spacing condition
        current_price = float(market_data.close_price)
        if current_price <= trading_context.lowest_buy * (1 - self.grid_drop_pct):
            return True  # Buy at a lower grid level

        return False
