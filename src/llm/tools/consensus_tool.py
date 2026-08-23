from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.trade_action import TradeAction
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.session.session_manager import SessionManager


class ConsensusInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )
    action: str = Field(description="Trade action to evaluate: 'BUY' or 'SELL'.")


class ConsensusTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_consensus"
    description: str = (
        "Evaluates the strategy consensus for a SINGLE asset and action (BUY/SELL), "
        "returning per-strategy votes, weights, quorum, and vote ratios."
    )
    args_schema: Type[BaseModel] = ConsensusInput
    consensus_manager: ConsensusManager
    session_manager: SessionManager
    market_data_manager: MarketDataManager
    assets: list = []

    def __init__(
            self,
            consensus_manager: ConsensusManager,
            session_manager: SessionManager,
            market_data_manager: MarketDataManager,
            assets: list,
    ):
        super().__init__(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=assets,
        )

    def _run(self, ticker_symbol: str, action: str) -> str:
        target = ticker_symbol.strip()
        asset = next((a for a in self.assets if a.ticker_symbol == target), None)
        if not asset:
            return f"Error: Asset {target} not found. Available: {sorted(a.ticker_symbol for a in self.assets)}"

        try:
            trade_action = TradeAction(action.strip().upper())
        except ValueError:
            return f"Error: action must be 'BUY' or 'SELL', got {action!r}."

        self.app_logger.info(f"Consensus for {asset.ticker_symbol} {trade_action.value} requested by LLM.")

        session = self.session_manager.current_session
        if not session:
            return "Error: No active trading session."
        context = session.trading_contexts.get(asset.key)
        if context is None:
            return f"Error: No trading context for {asset.ticker_symbol}."

        try:
            market_data = self.market_data_manager.get_market_data(asset)
            candles = self.market_data_manager.get_candles(asset)
            decision = self.consensus_manager.evaluate(
                trade_action, asset.ticker_symbol, context, market_data, candles
            )
        except Exception as exc:  # pylint: disable=broad-except
            return f"Error evaluating consensus for {asset.ticker_symbol}: {exc}"

        votes = ", ".join(f"{name}={vote}" for name, vote in decision.votes.items())
        return (
            f"Consensus [{decision.ticker_symbol} {decision.trade_action.value}]:\n"
            f"  Votes: {votes}\n"
            f"  Quorum: {decision.quorum} ({decision.true_count}/{decision.total})\n"
            f"  Vote ratio: {decision.vote_ratio:.3f}\n"
            f"  Weighted vote ratio: {decision.weighted_vote_ratio:.3f}\n"
            f"  Threshold: {decision.quorum_threshold:.3f}\n"
            f"  Margin: {decision.quorum_margin:.3f}\n"
            f"  Factor: {decision.factor}"
        )
