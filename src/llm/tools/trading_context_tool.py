from decimal import Decimal
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class TradingContextInput(BaseModel):
    ticker_symbol: str = Field(description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list.")


def format_decimal(val: Any) -> str:
    if val is None:
        return "None"
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            return str(val)
    if val == Decimal('inf') or val == Decimal('-inf'):
        return str(val)
    s = f"{val:f}"
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
        if s == "" or s.endswith('.'):
            s += "0"
    return s


class TradingContextTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_trading_context"
    description: str = (
        "Returns the current trading context (balances, open/closed positions) for a SINGLE given asset. "
        "Call this tool multiple times if you need to check multiple assets."
    )
    args_schema: Type[BaseModel] = TradingContextInput
    session_manager: Any

    def __init__(self, session_manager: Any):
        super().__init__(session_manager=session_manager)

    def _run(self, ticker_symbol: str) -> str:  # pylint: disable=arguments-differ
        target_symbol = ticker_symbol.strip()

        if not self.session_manager.current_session:
            return "Error: No active trading session."

        target_ctx = None
        for ctx in self.session_manager.current_session.trading_contexts.values():
            if ctx.ticker_symbol == target_symbol:
                target_ctx = ctx
                break

        if not target_ctx:
            available = [
                ctx.ticker_symbol
                for ctx in self.session_manager.current_session.trading_contexts.values()
            ]
            return (
                f"Error: Asset {target_symbol} not found in current session. "
                f"Available: {available}"
            )

        open_positions_str = "None"
        if target_ctx.open_positions:
            open_positions_list = []
            for p in target_ctx.open_positions:
                pos_str = (
                    f"MarketData(close_price={format_decimal(p.close_price)}, "
                    f"high_price={format_decimal(p.high_price)}, "
                    f"low_price={format_decimal(p.low_price)}, "
                    f"volume={format_decimal(p.volume)}, "
                    f"timestamp={p.timestamp})"
                )
                open_positions_list.append(pos_str)
            open_positions_str = "\n  - ".join(open_positions_list)
            open_positions_str = "\n  - " + open_positions_str

        close_positions_str = "None"
        if target_ctx.close_positions:
            close_positions_list = []
            for p in target_ctx.close_positions:
                pos_str = (
                    f"MarketData(close_price={format_decimal(p.close_price)}, "
                    f"high_price={format_decimal(p.high_price)}, "
                    f"low_price={format_decimal(p.low_price)}, "
                    f"volume={format_decimal(p.volume)}, "
                    f"timestamp={p.timestamp})"
                )
                close_positions_list.append(pos_str)
            close_positions_str = "\n  - ".join(close_positions_list)
            close_positions_str = "\n  - " + close_positions_str

        context_report = (
            f"Trading Context for {target_symbol} on {target_ctx.exchange}:\n"
            f"Balances:\n"
            f"  Starting Balance: {format_decimal(target_ctx.starting_balance)}\n"
            f"  Available Balance: {format_decimal(target_ctx.available_balance)}\n"
            f"  Closing Balance: {format_decimal(target_ctx.closing_balance)}\n"
            f"Current Position:\n"
            f"  Position Qty: {format_decimal(target_ctx.position_qty)}\n"
            f"  Avg Entry Price: {format_decimal(target_ctx.avg_entry_price)}\n"
            f"  Realized PnL: {format_decimal(target_ctx.realized_pnl)}\n"
            f"  Exit Qty: {format_decimal(target_ctx.exit_qty)}\n"
            f"  Avg Exit Price: {format_decimal(target_ctx.avg_exit_price)}\n"
            f"Open Positions Details: {open_positions_str}\n"
            f"Closed Positions Details: {close_positions_str}\n"
            f"Lowest Buy Price: {format_decimal(target_ctx.lowest_buy)}\n"
            f"Highest Buy Price: {format_decimal(target_ctx.highest_buy)}\n"
            f"Lowest Sell Price: {format_decimal(target_ctx.lowest_sell)}\n"
            f"Highest Sell Price: {format_decimal(target_ctx.highest_sell)}\n"
            f"Last Market Activity Time: {target_ctx.last_market_activity_time}"
        )

        self.app_logger.info("Trading context for LLM:")
        self.app_logger.warning(context_report)
        return context_report
