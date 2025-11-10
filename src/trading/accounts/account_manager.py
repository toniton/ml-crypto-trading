from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.trading_context import TradingContext
from src.core.registries.provider_registry import ProviderRegistry
from src.trading.context.trading_context_manager import TradingContextManager


class AccountManager(ProviderRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets

    def init_account_balances(self, trading_context_manager: TradingContextManager):
        for asset in self.assets:
            exchange = asset.exchange
            ticker_symbol = asset.ticker_symbol
            provider = self.get_provider(exchange.value)
            account_balance = provider.get_account_balance(ticker_symbol)
            opening_balance = account_balance.available_balance
            trading_context_manager.register_trading_context(
                asset.key, TradingContext(starting_balance=opening_balance)
            )

    def get_balance(self, ticker_symbol: str, provider_name: str) -> AccountBalance:
        provider = self.get_provider(provider_name)
        return provider.get_account_balance(ticker_symbol)
