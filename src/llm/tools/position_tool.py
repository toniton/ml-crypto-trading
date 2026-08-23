from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.llm.tools.trading_context_tool import format_decimal
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.session.session_manager import SessionManager


class PositionInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )


class PositionTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_position"
    description: str = (
        "Returns the current position snapshot (quantity, entry/exit prices, realized PnL, "
        "open/closed position counts) for a SINGLE asset."
    )
    args_schema: Type[BaseModel] = PositionInput
    session_manager: SessionManager
    assets: list = []

    def __init__(self, session_manager: SessionManager, assets: list):
        super().__init__(session_manager=session_manager, assets=assets)

    def _run(self, ticker_symbol: str) -> str:
        if not self.session_manager.current_session:
            return "Error: No active trading session."

        target = (ticker_symbol or "").strip()
        ctx = next(
            (
                context
                for context in self.session_manager.current_session.trading_contexts.values()
                if context.ticker_symbol == target
            ),
            None,
        )
        if not ctx:
            return (
                f"Error: Asset {target} not found in current session. "
                f"Available: {sorted(a.ticker_symbol for a in self.assets)}"
            )

        self.app_logger.info(f"Position for {target} requested by LLM.")
        return (
            f"Position for {ctx.ticker_symbol} on {ctx.exchange}:\n"
            f"  Position Qty: {format_decimal(ctx.position_qty)}\n"
            f"  Avg Entry Price: {format_decimal(ctx.avg_entry_price)}\n"
            f"  Avg Exit Price: {format_decimal(ctx.avg_exit_price)}\n"
            f"  Realized PnL: {format_decimal(ctx.realized_pnl)}\n"
            f"  Open Positions: {len(ctx.open_positions)}\n"
            f"  Closed Positions: {len(ctx.close_positions)}"
        )
