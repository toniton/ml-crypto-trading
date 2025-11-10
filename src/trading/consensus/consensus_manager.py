import logging

from api.interfaces.candle import Candle
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

    def get_quorum(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        if trade_action not in self.strategies:
            return False

        consensus_factor = 1.3 if trade_action == TradeAction.BUY else 1

        votes: list[bool] = []
        for strategy in self.strategies[trade_action]:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes.append(vote)
            logging.warning("Strategy: %s Vote: %s", strategy.__class__.__name__, vote)

        if votes.count(True) >= consensus_factor * votes.count(False):
            logging.warning("Quorum reached: %s %s", trade_action, votes)
            return True
        logging.warning("Quorum not reached: %s %s", trade_action, votes)
        return False
