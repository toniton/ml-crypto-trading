import logging
import threading
from queue import Queue
from uuid import uuid4

from api.interfaces.asset import Asset
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from database.unit_of_work import UnitOfWork
from database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.trading.helpers.trading_helper import TradingHelper


class OrderManager(RestClientRegistry, WebSocketRegistry):
    def __init__(self, unit_of_work: UnitOfWork):
        super().__init__()
        self.unit_of_work = unit_of_work
        self.order_queue = Queue()
        execute_thread = threading.Thread(target=self.process_order_queue, daemon=True)
        execute_thread.start()

    def process_order_queue(self):
        while True:
            order = self.order_queue.get()
            logging.debug(["Order queue msg", order])
            try:
                self.execute_order(order)
            except RuntimeError as exc:
                logging.error([f"Executing order failed. Order={order} . ->", exc])

    def _save_orders_to_database(self, orders: list[Order]) -> None:
        for order in orders:
            logging.warning(["Order update received, saving to DB", order])
            order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
            order_repository.upsert(order)
        self.unit_of_work.complete()

    def init_websocket(self, assets: list[Asset]):
        for asset in assets:
            websocket_client = self.get_websocket(asset.exchange.name)
            instrument_name = TradingHelper.format_ticker_symbol(asset.ticker_symbol, separator="_")
            websocket_client.subscribe_order_update(
                instrument_name, callback=self._save_orders_to_database
            )

    def open_order(
            self, ticker_symbol: str, provider_name: str, quantity: str,
            price: str, trade_action: TradeAction,
            timestamp: float, uuid: str = str(uuid4())
    ):
        order = Order(
            uuid=uuid,
            price=price,
            quantity=quantity,
            provider_name=provider_name,
            trade_action=trade_action,
            ticker_symbol=ticker_symbol,
            created_time=timestamp
        )
        self.order_queue.put(order)
        return order

    def execute_order(self, order: Order):
        provider = self.get_client(order.provider_name)
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
            raise RuntimeError("Error executing order:", order, exc) from exc

    def cancel_order(self, open_order: Order, market_price: str) -> Order:
        raise NotImplementedError("Unable to cancel order:", open_order)

    def get_closing_orders(self, ticker_symbol: str, price: str) -> list[Order]:
        order_repository = self.unit_of_work.get_repository(PostgresOrderRepository)
        return order_repository.get_by_price(ticker_symbol, price)
