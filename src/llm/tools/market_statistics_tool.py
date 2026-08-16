from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.llm.tools.trading_context_tool import format_decimal
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.markets.market_data_manager import MarketDataManager


class MarketStatisticsInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )


class MarketStatisticsTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_market_statistics"
    description: str = (
        "Returns the latest market statistics (close price, high price, low price, volume) "
        "for a SINGLE given asset."
    )
    args_schema: Type[BaseModel] = MarketStatisticsInput
    market_data_manager: MarketDataManager
    assets: list = []

    def __init__(self, market_data_manager: MarketDataManager, assets: list):
        super().__init__(
            market_data_manager=market_data_manager,
            assets=assets
        )

    def _run(self, ticker_symbol: str) -> str:
        target_symbol = ticker_symbol.strip()

        # Find the asset object
        asset = next((a for a in self.assets if a.ticker_symbol == target_symbol), None)
        if not asset:
            return f"Error: Asset {target_symbol} not found. Available: {[a.ticker_symbol for a in self.assets]}"

        try:
            market_data = self.market_data_manager.get_market_data(asset)
            if not market_data:
                return f"Error: No market data found for asset {target_symbol}."

            market_data_info = (
                f"Market Statistics for {target_symbol} on {asset.exchange.value}:\n"
                f"  Close Price: {format_decimal(market_data.close_price)}\n"
                f"  High Price: {format_decimal(market_data.high_price)}\n"
                f"  Low Price: {format_decimal(market_data.low_price)}\n"
                f"  Trading Volume: {format_decimal(market_data.volume)}\n"
                f"  Timestamp: {market_data.timestamp}"
            )
            self.app_logger.info(f"Market statistics for {target_symbol} requested by LLM.")
            return market_data_info
        except Exception as e:
            err_msg = f"Error fetching market statistics for {target_symbol}: {e}"
            self.app_logger.error(err_msg)
            return err_msg
