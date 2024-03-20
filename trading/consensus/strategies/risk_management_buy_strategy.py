from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from trading.consensus.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class RiskManagementBuyStrategy(RuleBasedTradingStrategy):

    def __init__(self, risk_tolerance=0.02):
        super().__init__()
        self.risk_tolerance = risk_tolerance
        self.type = TradeAction.BUY

    def get_quorum(
        self, trade_action: TradeAction,
        ticker_symbol: str, trading_context: TradingContext,
        market_data: MarketData
    ):
        risk_per_trade = trading_context.available_balance * self.risk_tolerance
        quantity = 1
        # if (quantity * float(market_data.close_price)) > risk_per_trade:
        #     return False
        return True
