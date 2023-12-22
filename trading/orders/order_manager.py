import decimal

from entities.trade_action import TradeAction
from trading.orders.providers.exchange_provider import ExchangeProvider


class OrderManager:
    providers: dict[str, ExchangeProvider]
    cached_balance: dict[str, decimal]

    def register_provider(self, provider: ExchangeProvider) -> decimal:
        if self.providers[provider.get_provider_name()] is provider:
            raise Exception(f"Provider ${provider.get_provider_name()} already registered.")
        self.providers[provider.get_provider_name()] = provider

    def get_price(self, ticker_symbol: str, provider_name: str) -> decimal:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")
        return provider.get_market_price(ticker_symbol)

    def open_order(self, ticker_symbol: str, provider_name: str, quantity: int):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")
        provider.place_order(ticker_symbol, quantity, TradeAction.BUY)

    def execute_order(self, ticker_symbol: str, provider_name: str, quantity: int):
        raise Exception(f"Not yet implemented!")

    def close_order(self, ticker_symbol: str, provider_name: str, quantity: int):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")
        provider.place_order(ticker_symbol, quantity, TradeAction.SELL)
