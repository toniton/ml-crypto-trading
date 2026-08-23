from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.core.interfaces.trading_journal import TradingJournal
from src.llm.tools.trading_context_tool import format_decimal
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class RecentTradesInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )
    limit: int = Field(default=20, description="Maximum number of most recent trades to return.")


class RecentTradesTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_recent_trades"
    description: str = (
        "Returns the most recent COMPLETED trades (fills) for a SINGLE asset from the current session."
    )
    args_schema: Type[BaseModel] = RecentTradesInput
    trading_journal: TradingJournal
    assets: list = []

    def __init__(self, trading_journal: TradingJournal, assets: list):
        super().__init__(trading_journal=trading_journal, assets=assets)

    def _run(self, ticker_symbol: str, limit: int = 20) -> str:
        asset = next((a for a in self.assets if a.ticker_symbol == ticker_symbol.strip()), None)
        if not asset:
            return f"Error: Asset {ticker_symbol} not found."

        self.app_logger.info(f"Recent trades for {ticker_symbol} requested by LLM.")
        entries = self.trading_journal.entries(ticker_symbol)
        if not entries:
            return f"No completed trades found for {ticker_symbol}."

        recent = entries[-limit:]
        lines = [f"Recent trades for {ticker_symbol} ({len(recent)} shown):"]
        for order in recent:
            lines.append(
                f"  {order.trade_action.value} qty={format_decimal(order.quantity)} "
                f"price={format_decimal(order.price)} status={order.status.value} "
                f"exchange={order.provider_name}"
            )
        return "\n".join(lines)
