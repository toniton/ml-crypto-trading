from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class TradingContextInput(BaseModel):
    ticker_symbol: str = Field(description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list.")


class TradingContextTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_trading_context"
    description: str = "Returns the current trading context for a SINGLE given asset. Call this tool multiple times if you need to check multiple assets."
    args_schema: Type[BaseModel] = TradingContextInput
    session_manager: Any

    def __init__(self, session_manager: Any):
        super().__init__(session_manager=session_manager)

    def _run(self, ticker_symbol: str) -> str:
        target_symbol = ticker_symbol.strip()

        if not self.session_manager.current_session:
            return "Error: No active trading session."

        # Search for the context matching the ticker_symbol
        for ctx in self.session_manager.current_session.trading_contexts.values():
            if ctx.ticker_symbol == target_symbol:
                self.app_logger.info("Trading context for LLM:")
                self.app_logger.warning(str(ctx))
                return str(ctx)

        return f"Error: Asset {target_symbol} not found in current session. Available: {[ctx.ticker_symbol for ctx in self.session_manager.current_session.trading_contexts.values()]}"
