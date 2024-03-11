from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_strategy import TradingStrategy
from api.interfaces.trading_context import TradingContext


class ConsensusManager:

    def __init__(self):
        self.strategies = {}

    def register_strategy(self, strategy: TradingStrategy):
        if strategy.type not in self.strategies:
            self.strategies[strategy.type] = []
        self.strategies[strategy.type].append(strategy)

    def unregister_strategy(self, strategy: TradingStrategy):
        if strategy.type in self.strategies:
            self.strategies[strategy.type].remove(strategy)
            if len(self.strategies[strategy.type]) == 0:
                del self.strategies[strategy.type]

    # TODO: Add quantity to get_quorum, for better risk management.
    def get_quorum(
        self,
        trade_action: TradeAction, ticker_symbol: str,
        trading_context: TradingContext,
        market_data: MarketData
    ):
        if trade_action not in self.strategies:
            return False

        votes: list[bool] = []
        for strategy in self.strategies[trade_action]:
            votes.append(
                strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data)
            )

        if votes.count(True) >= 2 * votes.count(False):
            return True
        return False
