import decimal
import logging
import time
from uuid import uuid4

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.timeframe import Timeframe
from database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from database.unit_of_work import UnitOfWork
from src.core.registries.provider_registry import ProviderRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.trading.helpers.trading_helper import TradingHelper


class OrderManager(ProviderRegistry, WebSocketRegistry):
    cached_balance: dict[str, decimal]

    def __init__(self, unit_of_work: UnitOfWork):
        super().__init__()
        self.unit_of_work = unit_of_work

    def init_websocket(self, assets: list[Asset]):
        for asset in assets:
            websocket_client = self.get_websocket(asset.exchange.name)
            instrument_name = TradingHelper.format_ticker_symbol(asset.ticker_symbol, separator="_")
            websocket_client.subscribe_order_update(instrument_name, callback=lambda data: logging.warning([f"Order update received", data]))

    def get_market_data(self, ticker_symbol: str, provider_name: str) -> MarketData:
        provider = self.get_provider(provider_name)
        return provider.get_market_data(ticker_symbol)

    def get_candles(self, provider_name: str, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        provider = self.get_provider(provider_name)
        return provider.get_candle(ticker_symbol, timeframe)

    def open_order(self, ticker_symbol: str, provider_name: str, quantity: str, price: str):
        provider = self.get_provider(provider_name)
        order = Order(
            uuid=uuid4(),
            price=price,
            quantity=quantity,
            provider_name=provider_name,
            trade_action=TradeAction.BUY,
            ticker_symbol=ticker_symbol,
            created_time=time.time()
        )

        return order

    def execute_order(self, order: Order):
        # Pass in exchange, so we can have proper db storage.
        provider = self.get_provider(order.provider_name)

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

    def close_order(self, open_order: Order, market_price: str) -> Order:
        provider = self.get_provider(open_order.provider_name)
        order = Order(
            uuid=open_order.uuid,
            price=market_price,
            quantity=open_order.quantity,
            provider_name=open_order.provider_name,
            trade_action=TradeAction.SELL,
            ticker_symbol=open_order.ticker_symbol,
            created_time=time.time()
        )
        try:
            order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
            order_repository.save(order)
            self.unit_of_work.complete()
        except Exception:
            logging.warning(f"Error saving order to database on close order: %s", order)

        return order

    def get_closing_orders(self, ticker_symbol: str, price: str) -> list[Order]:
        order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
        return order_repository.get_by_price(ticker_symbol, price)
