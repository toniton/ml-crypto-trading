from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.trading_strategy import TradingStrategy
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.consensus.consensus_factor import ConsensusFactor


class ConsensusManager(ApplicationLoggingMixin):

    def __init__(self, consensus_factor: ConsensusFactor):
        self.strategies = {}
        self.consensus_factor = consensus_factor

    def register_strategy(self, strategy: TradingStrategy):
        if strategy.type not in self.strategies:
            self.strategies[strategy.type] = []
        self.strategies[strategy.type].append(strategy)

    def update_factor(self, consensus_factor: ConsensusFactor) -> None:
        self.consensus_factor = consensus_factor

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

        consensus_factor = self.consensus_factor.buy if trade_action == TradeAction.BUY else self.consensus_factor.sell

        votes: list[bool] = []
        for strategy in self.strategies[trade_action]:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes.append(vote)
            self.app_logger.debug(f"Strategy: {strategy.__class__.__name__} Vote: {vote}")

        if votes.count(True) >= consensus_factor * votes.count(False):
            self.app_logger.info(f"Quorum reached: {ticker_symbol} {trade_action} {votes}")
            return True
        self.app_logger.info(f"Quorum not reached: {ticker_symbol} {trade_action} {votes}")
        return False

    def get_consensus_score(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ) -> float:
        if trade_action not in self.strategies or not self.strategies[trade_action]:
            return 0.0

        votes: list[bool] = []
        for strategy in self.strategies[trade_action]:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes.append(vote)

        return float(votes.count(True)) / len(votes)
