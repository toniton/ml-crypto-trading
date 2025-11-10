from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from src.core.registries.provider_registry import ProviderRegistry


class AccountManager(ProviderRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets

    def get_balance(self, ticker_symbol: str, provider_name: str) -> AccountBalance:
        provider = self.get_provider(provider_name)
        return provider.get_account_balance(ticker_symbol)
