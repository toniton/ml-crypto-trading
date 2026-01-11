import queue
import threading
from queue import Queue
from uuid import uuid4

from api.interfaces.asset import Asset
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from api.interfaces.trade_action import OrderStatus
from database.database_manager import DatabaseManager
from database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.core.interfaces.trading_journal import TradingJournal
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.clients.websocket_manager import WebSocketManager


class OrderManager(ApplicationLoggingMixin, RestClientRegistry, WebSocketRegistry):
    def __init__(
            self, database_manager: DatabaseManager, trading_journal: TradingJournal,
            websocket_manager: WebSocketManager
    ):
        super().__init__()
        self._database_manager = database_manager
        self._websocket_manager = websocket_manager
        self._order_queue = Queue()
        self._trading_journal = trading_journal
        self._assets = []
        self._stop_event = threading.Event()
        self._execute_thread = threading.Thread(target=self.process_order_queue, daemon=True)
        self._execute_thread.start()

    def process_order_queue(self):
        self.app_logger.info("Order processing thread started")
        while not self._stop_event.is_set():
            try:
                order = self._order_queue.get(timeout=0.1)
                self.app_logger.debug(f"Order queue processing: {order}")
                try:
                    self.execute_order(order)
                    self.app_logger.info(f"Order executed: {order.uuid}")
                except RuntimeError as exc:
                    self.app_logger.error(f"Executing order failed. Order={order}: {exc}", exc_info=True)
            except queue.Empty:
                pass
        self.app_logger.info("Order processing thread exiting")

    def _stop_order_executions(self):
        self.app_logger.info("Stopping order executions...")
        self._stop_event.set()
        if hasattr(self, '_execute_thread') and self._execute_thread.is_alive():
            self._execute_thread.join(timeout=5)
            if self._execute_thread.is_alive():
                self.app_logger.warning("Order execution thread failed to terminate in time.")

    def _save_orders_to_database(self, orders: list[Order]) -> None:
        try:
            with self._database_manager.get_unit_of_work() as uow:
                for order in orders:
                    self.app_logger.debug(f"Order update received, saving to DB: {order}")
                    if order.status == OrderStatus.COMPLETED:
                        self._trading_journal.record_fill(order)
                    order_repository = uow.get_repository(PostgresOrderRepository)
                    order_repository.upsert(order)
        except Exception as e:
            self.app_logger.error(f"Failed to save orders: {e}", exc_info=True)
            raise

    def initialize(self, assets: list[Asset]):
        self._assets = assets
        self._init_websocket(assets)
        self._update_pending_orders()

    def _init_websocket(self, assets: list[Asset]):
        for asset in assets:
            self._websocket_manager.subscribe_order_update(
                exchange=asset.exchange.value,
                instrument_name=asset.ticker_symbol,
                callback=self._save_orders_to_database
            )

    def _update_pending_orders(self):
        pending_orders = self._get_pending_orders()
        updated_orders = []
        for order in pending_orders:
            provider = self.get_client(order.provider_name)
            try:
                updated_orders.append(provider.get_order(order.uuid))
            except Exception as exc:
                raise RuntimeError("Unable to update pending order:", order) from exc
        self._save_orders_to_database(updated_orders)

    def open_order(
            self, ticker_symbol: str, provider_name: str, quantity: str,
            price: str, trade_action: TradeAction,
            timestamp: float, uuid: str = None
    ):
        order = Order(
            uuid=uuid or str(uuid4()),
            price=price,
            quantity=quantity,
            provider_name=provider_name,
            trade_action=trade_action,
            ticker_symbol=ticker_symbol,
            created_time=timestamp
        )
        self._order_queue.put(order)
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
            with self._database_manager.get_unit_of_work() as uow:
                order_repository = uow.get_repository(PostgresOrderRepository)
                order_repository.upsert(order)
        except Exception as exc:
            raise RuntimeError("Error executing and/or saving order:", order, exc) from exc

    def _cancel_order(self, open_order: Order) -> None:
        provider = self.get_client(open_order.provider_name)
        try:
            provider.cancel_order(open_order.uuid)
        except Exception as exc:
            raise RuntimeError("Unable to cancel order:", open_order) from exc

    def _get_pending_orders(self) -> list[Order]:
        with self._database_manager.get_unit_of_work() as uow:
            order_repository = uow.get_repository(PostgresOrderRepository)
            return order_repository.get_by_status(OrderStatus.PENDING)

    def _cancel_pending_orders(self):
        pending_orders = self._get_pending_orders()
        for order in pending_orders:
            self._cancel_order(order)

    def shutdown(self):
        self._stop_order_executions()
        self._cancel_pending_orders()
        for asset in self._assets:
            self._websocket_manager.unsubscribe_order_update(
                exchange=asset.exchange.value,
                instrument_name=asset.ticker_symbol
            )
