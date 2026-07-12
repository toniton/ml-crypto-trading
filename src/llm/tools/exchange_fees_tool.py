from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.llm.tools.trading_context_tool import format_decimal
from src.trading.fees.fees_manager import FeesManager


class ExchangeFeesInput(BaseModel):
    ticker_symbol: str = Field(description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list.")


class ExchangeFeesTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_exchange_fees"
    description: str = "Returns the exchange fees (maker and taker fee percentages) for a SINGLE given asset."
    args_schema: Type[BaseModel] = ExchangeFeesInput
    fees_manager: FeesManager
    assets: list = []

    def __init__(self, fees_manager: FeesManager, assets: list):
        super().__init__(
            fees_manager=fees_manager,
            assets=assets
        )

    def _run(self, ticker_symbol: str) -> str:
        target_symbol = ticker_symbol.strip()

        # Find the asset object
        asset = next((a for a in self.assets if a.ticker_symbol == target_symbol), None)
        if not asset:
            return f"Error: Asset {target_symbol} not found. Available: {[a.ticker_symbol for a in self.assets]}"

        try:
            fees = self.fees_manager.get_instrument_fees(asset.exchange.value, asset.ticker_symbol)
            if not fees:
                return f"Error: No fees found for asset {target_symbol}."

            fee_info = (
                f"Exchange Fees for {target_symbol} on {asset.exchange.value}:\n"
                f"  Maker Fee Pct: {format_decimal(fees.maker_fee_pct)}%\n"
                f"  Taker Fee Pct: {format_decimal(fees.taker_fee_pct)}%"
            )
            self.app_logger.info(f"Exchange fees for {target_symbol} requested by LLM.")
            return fee_info
        except Exception as e:
            err_msg = f"Error fetching fees for {target_symbol}: {e}"
            self.app_logger.error(err_msg)
            return err_msg
