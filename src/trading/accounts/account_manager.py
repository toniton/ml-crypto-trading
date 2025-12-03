import logging

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.trading_context import TradingContext
from src.core.registries.provider_registry import ProviderRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.trading.context.trading_context_manager import TradingContextManager


class AccountManager(ProviderRegistry, WebSocketRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.balances = {}

    def _cache_balances(self, provider_name: str, balances: list[AccountBalance]) -> None:
        if provider_name not in self.balances:
            self.balances[provider_name] = {}

        for balance in balances:
            self.balances[provider_name][balance.currency] = balance

        logging.warning(f"Updated balances for {provider_name}: {self.balances[provider_name]}")

    def init_websocket(self):
        for provider_name, websocket in self.websockets.items():
            websocket.subscribe_balance(
                callback=lambda data, provider=provider_name: self._cache_balances(provider, data)
            )

    def init_account_balances(self, trading_context_manager: TradingContextManager):
        for asset in self.assets:
            exchange = asset.exchange
            quote_ticker_symbol = asset.ticker_symbol
            try:
                opening_balance = self.get_balance(quote_ticker_symbol, exchange.value)
                trading_context_manager.register_trading_context(
                    asset.key, TradingContext(starting_balance=opening_balance.available_balance)
                )
            except Exception:
                logging.error(f"Unable to initialize account balance for {asset} from {exchange}")

    def get_balance(self, currency_symbol: str, provider_name: str) -> AccountBalance:
        if provider_name in self.balances and currency_symbol in self.balances[provider_name]:
            return self.balances[provider_name][currency_symbol]
        provider = self.get_provider(provider_name)
        data = provider.get_account_balance()
        self._cache_balances(provider_name, data)
        return self.balances[provider_name][currency_symbol] or AccountBalance(currency_symbol, 0)
