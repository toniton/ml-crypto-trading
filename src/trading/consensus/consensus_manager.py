from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.trading_strategy import TradingStrategy
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.consensus.consensus_factor import ConsensusFactor


class ConsensusManager(ApplicationLoggingMixin):

    def __init__(self, consensus_factor: ConsensusFactor):
        self.strategies = {}
        self.consensus_factor = consensus_factor

    def register_strategy(self, strategy: TradingStrategy):
        if strategy.ticker_symbols is not None and not strategy.ticker_symbols:
            raise ValueError(
                f"Strategy '{strategy.name}' is not bound to any ticker symbol; refusing to register"
            )
        if strategy.action not in self.strategies:
            self.strategies[strategy.action] = []
        self.strategies[strategy.action].append(strategy)

    def update_factor(self, consensus_factor: ConsensusFactor) -> None:
        self.consensus_factor = consensus_factor

    def unregister_strategy(self, strategy: TradingStrategy):
        if strategy.action in self.strategies:
            self.strategies[strategy.action].remove(strategy)
            if len(self.strategies[strategy.action]) == 0:
                del self.strategies[strategy.action]

    @staticmethod
    def _eligible_strategies(strategies: list[TradingStrategy], ticker_symbol: str) -> list[TradingStrategy]:
        return [
            strategy
            for strategy in strategies
            if strategy.ticker_symbols is None or ticker_symbol in strategy.ticker_symbols
        ]

    def get_quorum(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        if trade_action not in self.strategies:
            self.app_logger.info(
                f"Consensus [{ticker_symbol} {trade_action.value}]: no strategies registered -> Quorum=False"
            )
            return False

        strategies = self._eligible_strategies(self.strategies[trade_action], ticker_symbol)
        if not strategies:
            self.app_logger.info(
                f"Consensus [{ticker_symbol} {trade_action.value}]: no strategies registered -> Quorum=False"
            )
            return False

        consensus_factor = self.consensus_factor.buy if trade_action == TradeAction.BUY else self.consensus_factor.sell

        votes: dict[str, bool] = {}
        for strategy in strategies:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes[strategy.name] = vote
            self.app_logger.debug(f"Strategy: {strategy.name} Vote: {vote}")

        true_count = sum(1 for vote in votes.values() if vote)
        total = len(votes)
        quorum = true_count >= consensus_factor * (total - true_count)
        votes_str = ", ".join(f"{name}={vote}" for name, vote in votes.items())
        self.app_logger.info(
            f"Consensus [{ticker_symbol} {trade_action.value}]: {votes_str} -> Quorum={quorum} ({true_count}/{total})"
        )
        return quorum

    def get_consensus_score(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ) -> float:
        if trade_action not in self.strategies:
            return 0.0

        strategies = self._eligible_strategies(self.strategies[trade_action], ticker_symbol)
        if not strategies:
            return 0.0

        votes: list[bool] = []
        for strategy in strategies:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes.append(vote)

        return float(votes.count(True)) / len(votes)
