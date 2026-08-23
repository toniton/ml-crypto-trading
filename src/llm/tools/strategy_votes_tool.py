from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.trade_action import TradeAction
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.session.session_manager import SessionManager


class StrategyVotesInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )
    action: str = Field(description="Trade action to evaluate: 'BUY' or 'SELL'.")


class StrategyVotesTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_strategy_votes"
    description: str = (
        "Returns the per-strategy votes for a SINGLE asset and action (BUY/SELL)."
    )
    args_schema: Type[BaseModel] = StrategyVotesInput
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

    def _run(self, ticker_symbol: str, action: str) -> str:  # pylint: disable=arguments-differ,too-many-return-statements
        target = ticker_symbol.strip()
        asset = next((a for a in self.assets if a.ticker_symbol == target), None)
        if not asset:
            return f"Error: Asset {target} not found. Available: {sorted(a.ticker_symbol for a in self.assets)}"

        try:
            trade_action = TradeAction(action.strip().upper())
        except ValueError:
            return f"Error: action must be 'BUY' or 'SELL', got {action!r}."

        self.app_logger.info(f"Strategy votes for {asset.ticker_symbol} {trade_action.value} requested by LLM.")

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

        if not decision.votes:
            return f"No strategies registered for {ticker_symbol} {trade_action.value}."

        votes = ", ".join(f"{name}={vote}" for name, vote in decision.votes.items())
        return f"Strategy votes [{decision.ticker_symbol} {decision.trade_action.value}]: {votes}"
