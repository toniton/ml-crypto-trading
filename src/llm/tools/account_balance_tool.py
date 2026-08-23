from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.llm.tools.trading_context_tool import format_decimal
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_manager import AccountManager


class AccountBalanceInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )


class AccountBalanceTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_account_balance"
    description: str = (
        "Returns the live account balances (base and quote currencies) for a SINGLE asset."
    )
    args_schema: Type[BaseModel] = AccountBalanceInput
    account_manager: AccountManager
    assets: list = []

    def __init__(self, account_manager: AccountManager, assets: list):
        super().__init__(account_manager=account_manager, assets=assets)

    def _run(self, ticker_symbol: str) -> str:  # pylint: disable=arguments-differ
        target = ticker_symbol.strip()
        asset = next((a for a in self.assets if a.ticker_symbol == target), None)
        if not asset:
            return f"Error: Asset {target} not found. Available: {sorted(a.ticker_symbol for a in self.assets)}"

        provider = asset.exchange.value
        try:
            base = self.account_manager.get_base_balance(asset, provider)
            quote = self.account_manager.get_quote_balance(asset, provider)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Error fetching account balance for {asset.ticker_symbol}: {exc}")
            return f"Error fetching account balance for {asset.ticker_symbol}: {exc}"

        self.app_logger.info(f"Account balance for {asset.ticker_symbol} requested by LLM.")
        return (
            f"Account Balance for {asset.ticker_symbol} on {provider}:\n"
            f"  Base ({base.currency}): {format_decimal(base.available_balance)}\n"
            f"  Quote ({quote.currency}): {format_decimal(quote.available_balance)}"
        )
