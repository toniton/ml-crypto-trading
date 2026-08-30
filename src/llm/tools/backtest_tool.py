from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.agent.backtest.backtest_service import BacktestService
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class BacktestInput(BaseModel):
    ticker_symbol: str = Field(
        description="Ticker symbol of the asset to backtest (e.g., 'BTC_USD')."
    )


class BacktestTool(BaseTool, ApplicationLoggingMixin):
    """LangChain tool that runs a backtest via :class:`BacktestService`.

    Returns a compact summary (session id, return, drawdown, trade counts) rather
    than the full result, so the LLM does not consume its context window.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "run_backtest"
    description: str = (
        "Run a backtest for a single asset over its available historical data and "
        "return a compact summary (session id, return, drawdown and trade counts)."
    )
    args_schema: Type[BaseModel] = BacktestInput
    backtest_service: BacktestService

    def __init__(self, backtest_service: BacktestService):
        super().__init__(backtest_service=backtest_service)

    def _run(self, ticker_symbol: str) -> str:  # pylint: disable=arguments-differ
        summary = self.backtest_service.run_asset(ticker_symbol)
        self.app_logger.info(f"Backtest for {ticker_symbol} requested by LLM: session={summary.session_id}")
        return (
            f"Backtest {summary.ticker_symbol} (session {summary.session_id}):\n"
            f"  Status: {summary.status}\n"
            f"  Return: {summary.return_pct:.4f}%\n"
            f"  PnL: {summary.absolute_pnl:.4f}\n"
            f"  Max drawdown: {summary.max_drawdown_pct:.4f}%\n"
            f"  Round trips: {summary.round_trips}\n"
            f"  Fills: {summary.orders_filled}\n"
            f"  Cancelled: {summary.orders_cancelled}"
        )
