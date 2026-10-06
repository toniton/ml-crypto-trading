from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.backtest_request import BacktestDataSourceType
from src.agent.backtest.backtest_service import BacktestService
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class BacktestInput(BaseModel):
    ticker_symbol: str = Field(
        description="Ticker symbol of the asset to backtest (e.g., 'BTC_USD')."
    )
    data_source: BacktestDataSourceType = Field(
        default=BacktestDataSourceType.CSV,
        description=(
            "Historical data source: 'csv' (configured CSV history) or "
            "'market_data' (recently recorded live market data)."
        ),
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

    def _run(  # pylint: disable=arguments-differ
            self,
            ticker_symbol: str,
            data_source: BacktestDataSourceType = BacktestDataSourceType.CSV,
    ) -> str:
        summary = self.backtest_service.run_asset(ticker_symbol, source_type=data_source)
        self.app_logger.info(f"Backtest for {ticker_symbol} requested by LLM: session={summary.session_id}")
        time_range = ""
        if summary.start_time and summary.end_time:
            fmt = "%Y-%m-%d %H:%M:%S UTC"
            time_range = f"  Time range: {summary.start_time.strftime(fmt)} to {summary.end_time.strftime(fmt)}\n"
        elif summary.start_time:
            fmt = "%Y-%m-%d %H:%M:%S UTC"
            time_range = f"  Start time: {summary.start_time.strftime(fmt)}\n"

        robustness = ""
        if summary.sharpe_ratio is not None:
            robustness += f"  Sharpe ratio: {summary.sharpe_ratio}\n"
        if summary.sortino_ratio is not None:
            robustness += f"  Sortino ratio: {summary.sortino_ratio}\n"
        if summary.profit_factor is not None:
            robustness += f"  Profit factor: {summary.profit_factor}\n"
        if summary.win_rate_pct is not None:
            robustness += f"  Win rate: {summary.win_rate_pct}%\n"

        return (
            f"Backtest {summary.ticker_symbol} (session {summary.session_id}):\n"
            f"  Status: {summary.status}\n"
            f"  Data points: {summary.data_points}\n"
            f"{time_range}"
            f"  Return: {summary.return_pct:.4f}%\n"
            f"  PnL: {summary.absolute_pnl:.4f}\n"
            f"  Max drawdown: {summary.max_drawdown_pct:.4f}%\n"
            f"{robustness}"
            f"  Round trips: {summary.round_trips}\n"
            f"  Fills: {summary.orders_filled}\n"
            f"  Cancelled: {summary.orders_cancelled}"
        )
