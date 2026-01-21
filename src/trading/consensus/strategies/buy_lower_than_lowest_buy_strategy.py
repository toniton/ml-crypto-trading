from decimal import Decimal

from api.interfaces.trade_action import TradeAction
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyLowerThanLowestBuyStrategy(RuleBasedTradingStrategy):
    def __init__(self, grid_spacing_pct=Decimal("0.5")):
        super().__init__()
        self.grid_spacing_pct = Decimal(str(grid_spacing_pct)) / Decimal("100")
        self.type = TradeAction.BUY

    def get_quorum(self, trade_action, _ticker_symbol, trading_context, market_data, _candles):
        if trade_action != TradeAction.BUY:
            return False

        if trading_context.lowest_buy == Decimal('inf'):
            return True

        threshold = trading_context.lowest_buy * (Decimal("1") - self.grid_spacing_pct)
        if market_data.close_price < threshold:
            return True  # Buy at a lower price than the lowest buy

        return False
