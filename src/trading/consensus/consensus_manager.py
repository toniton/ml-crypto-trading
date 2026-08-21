from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.trading_strategy import TradingStrategy
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.consensus.consensus_factor import ConsensusFactor


class ConsensusManager(ApplicationLoggingMixin):

    def __init__(self):
        self.strategies = {}
        self._asset_factors: dict[str, ConsensusFactor] = {}

    def set_factors(self, assets: list[Asset]) -> None:
        self._asset_factors = {
            asset.ticker_symbol: asset.consensus
            for asset in assets
            if asset.consensus is not None
        }

    def factor_for(self, ticker_symbol: str) -> Optional[ConsensusFactor]:
        return self._asset_factors.get(ticker_symbol)

    def register_strategy(self, strategy: TradingStrategy):
        if strategy.ticker_symbols is not None and not strategy.ticker_symbols:
            raise ValueError(
                f"Strategy '{strategy.name}' is not bound to any ticker symbol; refusing to register"
            )
        existing = self.strategies.get(strategy.action, [])
        for other in existing:
            if other.name != strategy.name:
                continue
            other_tickers = other.ticker_symbols
            new_tickers = strategy.ticker_symbols
            if other_tickers is None or new_tickers is None:
                raise ValueError(
                    f"Duplicate strategy name '{strategy.name}' for action "
                    f"{strategy.action.value}: unrestricted strategy already registered"
                )
            overlap = other_tickers & new_tickers
            if overlap:
                raise ValueError(
                    f"Duplicate strategy name '{strategy.name}' for action "
                    f"{strategy.action.value} and tickers {sorted(overlap)}"
                )
        if strategy.action not in self.strategies:
            self.strategies[strategy.action] = []
        self.strategies[strategy.action].append(strategy)

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

    def evaluate(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ) -> ConsensusDecision:
        if trade_action not in self.strategies:
            self.app_logger.info(
                f"Consensus [{ticker_symbol} {trade_action.value}]: no strategies registered -> Quorum=False"
            )
            return ConsensusDecision(
                trade_action=trade_action, ticker_symbol=ticker_symbol,
                votes={}, weights={}, factor=0.0
            )

        strategies = self._eligible_strategies(self.strategies[trade_action], ticker_symbol)
        if not strategies:
            self.app_logger.info(
                f"Consensus [{ticker_symbol} {trade_action.value}]: no strategies registered -> Quorum=False"
            )
            return ConsensusDecision(
                trade_action=trade_action, ticker_symbol=ticker_symbol,
                votes={}, weights={}, factor=0.0
            )

        consensus_factor = self.factor_for(ticker_symbol)
        if consensus_factor is None:
            raise ValueError(
                f"Asset '{ticker_symbol}' has no consensus factor configured; "
                f"consensus must be specified per asset."
            )
        factor = consensus_factor.buy if trade_action == TradeAction.BUY else consensus_factor.sell

        votes: dict[str, bool] = {}
        weights: dict[str, float] = {}
        for strategy in strategies:
            vote = strategy.get_quorum(trade_action, ticker_symbol, trading_context, market_data, candles)
            votes[strategy.name] = bool(vote)
            weights[strategy.name] = float(getattr(strategy, "weight", 1.0))
            self.app_logger.debug(f"Strategy: {strategy.name} Vote: {vote}")

        decision = ConsensusDecision(
            trade_action=trade_action, ticker_symbol=ticker_symbol,
            votes=votes, weights=weights, factor=factor
        )
        votes_str = ", ".join(f"{name}={vote}" for name, vote in votes.items())
        self.app_logger.info(
            f"Consensus [{ticker_symbol} {trade_action.value}]: {votes_str} "
            f"-> Quorum={decision.quorum} ({decision.true_count}/{decision.total})"
        )
        return decision

    def get_quorum(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ) -> bool:
        return self.evaluate(
            trade_action, ticker_symbol, trading_context, market_data, candles
        ).quorum
