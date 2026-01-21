from decimal import Decimal

from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyContextAwareGridStrategy(RuleBasedTradingStrategy):
    def __init__(self, grid_drop_pct=Decimal("0.5"), cooldown_seconds=60):
        super().__init__()
        self.grid_drop_pct = grid_drop_pct / Decimal("100")  # e.g. 0.5%
        self.cooldown_seconds = cooldown_seconds
        self.type = TradeAction.BUY

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.BUY:
            return False

        # If no previous buy, start the grid
        if trading_context.lowest_buy == Decimal('inf'):
            return True

        # Check grid spacing condition
        threshold = trading_context.lowest_buy * (Decimal("1") - self.grid_drop_pct)
        if market_data.close_price <= threshold:
            return True  # Buy at a lower grid level

        return False
