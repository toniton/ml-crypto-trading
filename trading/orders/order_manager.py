import decimal
from uuid import uuid4

from entities.market_data import MarketData
from entities.order import Order
from entities.trade_action import TradeAction
from repositories.providers.postgres_order_repository import PostgresOrderRepository
from trading.providers.exchange_provider import ExchangeProvider
from trading.unit_of_work import UnitOfWork


class OrderManager:
    KAFKA_TOPIC: str = "ORDERS_TOPIC"
    providers: dict[str, ExchangeProvider] = {}
    cached_balance: dict[str, decimal]

    def __init__(self, unit_of_work: UnitOfWork):
        self.unit_of_work = unit_of_work

    def register_provider(self, provider: ExchangeProvider):
        if provider.get_provider_name() in self.providers:
            raise Exception(f"Provider ${provider.get_provider_name()} already registered.")

        self.providers[provider.get_provider_name()] = provider

    def get_market_data(self, ticker_symbol: str, provider_name: str) -> MarketData:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        return provider.get_market_data(ticker_symbol)

    def open_order(self, ticker_symbol: str, provider_name: str, quantity: str, price: str):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        order = Order(
            uuid=uuid4(),
            price=price,
            quantity=quantity,
            provider_name=provider_name,
            trade_action=TradeAction.BUY,
            ticker_symbol=ticker_symbol
        )

        return order

    def execute_order(self, order: Order):
        # Pass in exchange, so we can have proper db storage.
        provider = self.providers.get(order.provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        try:
            provider.place_order(
                order.uuid,
                order.ticker_symbol,
                order.quantity,
                order.price,
                order.trade_action
            )
            order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
            order_repository.save(order)
            self.unit_of_work.complete()
        except Exception as exc:
            raise Exception(f"Error executing order:", order, exc)

    def close_order(self, ticker_symbol: str, provider_name: str, quantity: int, price: float):
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")

        order = Order(
            uuid=uuid4(),
            price=price,
            quantity=quantity,
            provider_name=provider_name,
            trade_action=TradeAction.SELL,
            ticker_symbol=ticker_symbol
        )

        return order

    def get_closing_orders(self, ticker_symbol: str, price: str) -> list[Order]:
        order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
        return order_repository.get_by_price(ticker_symbol, price)
