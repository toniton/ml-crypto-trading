import decimal
from uuid import uuid4

from entities.order import Order
from entities.trade_action import TradeAction
from trading.orders.providers.exchange_provider import ExchangeProvider


class OrderManager:
    providers: dict[str, ExchangeProvider] = {}
    cached_balance: dict[str, decimal]

    def register_provider(self, provider: ExchangeProvider) -> decimal:
        if provider.get_provider_name() in self.providers:
            raise Exception(f"Provider ${provider.get_provider_name()} already registered.")

        self.providers[provider.get_provider_name()] = provider

    def get_price(self, ticker_symbol: str, provider_name: str) -> decimal:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        return provider.get_market_price(ticker_symbol)

    def open_order(self, ticker_symbol: str, provider_name: str, quantity: int, price: float):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        order = Order()
        order.uuid = uuid4()
        order.trade_action = TradeAction.BUY
        order.price = price
        order.quantity = quantity
        order.provider_name = provider_name
        order.ticker_symbol = ticker_symbol

        return order

    def execute_order(self, order: Order):
        provider = self.providers.get(order.provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        provider.place_order(
            order.uuid,
            order.ticker_symbol,
            order.quantity,
            order.price,
            order.trade_action
        )

    def close_order(self, ticker_symbol: str, provider_name: str, quantity: int, price: float):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        order = Order()
        order.uuid = uuid4()
        order.trade_action = TradeAction.SELL
        order.price = price
        order.quantity = quantity
        order.provider_name = provider_name
        order.ticker_symbol = ticker_symbol

        return order
