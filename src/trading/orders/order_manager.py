import queue
import threading
from decimal import Decimal
from queue import Queue
from uuid import uuid4

from api.interfaces.asset import Asset
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from api.interfaces.trade_action import OrderStatus
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.core.interfaces.trading_journal import TradingJournal
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.exchange.managers.rest_manager import RestManager
from src.exchange.managers.websocket_manager import WebSocketManager


class OrderManager(ApplicationLoggingMixin):
    OPEN_STATUSES = {
        OrderStatus.PENDING,
        OrderStatus.PROCESSING,
    }

    def __init__(
            self, database_manager: DatabaseManager, trading_journal: TradingJournal,
            rest_manager: RestManager, websocket_manager: WebSocketManager
    ):
        self._database_manager = database_manager
        self._rest_manager = rest_manager
        self._websocket_manager = websocket_manager
        self._order_queue = Queue()
        self._trading_journal = trading_journal
        self._assets = []
        self._stop_event = threading.Event()
        self._execute_thread = threading.Thread(target=self.process_order_queue, daemon=True)
        self._execute_thread.start()

    def place_order(
            self,
            exchange: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action: TradeAction
    ) -> None:
        self._rest_manager.place_order(
            exchange, uuid, ticker_symbol, quantity, price, trade_action
        )

    def get_order(self, exchange: str, uuid: str) -> Order:
        return self._rest_manager.get_order(exchange, uuid)

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
        self.reconcile_pending_orders()

    def _init_websocket(self, assets: list[Asset]):
        for asset in assets:
            self._websocket_manager.subscribe_order_update(
                exchange=asset.exchange.value,
                instrument_name=asset.ticker_symbol,
                callback=self._save_orders_to_database
            )

    def get_open_orders(self, exchange: str, ticker_symbol: str = None) -> list[Order]:
        open_orders: list[Order] = []
        try:
            exchange_open_orders = self._rest_manager.get_open_orders(exchange, ticker_symbol)
            if exchange_open_orders:
                open_orders.extend(exchange_open_orders)
        except (RuntimeError, RuntimeWarning) as exc:
            self.app_logger.warning(f"Unable to fetch open orders from {exchange}: {exc}")
        except Exception as exc:
            self.app_logger.error(f"Unexpected error fetching open orders from {exchange}: {exc}", exc_info=True)
            raise RuntimeError("Unable to fetch open orders:", exchange) from exc
        return open_orders

    def reconcile_pending_orders(self):
        try:
            non_terminal_orders = self._get_non_terminal_orders()
        except Exception as exc:
            self.app_logger.warning(f"Unable to load non-terminal orders for reconciliation: {exc}")
            return

        for order in non_terminal_orders:
            try:
                exchange_order = self.get_order(order.provider_name, order.uuid)
            except Exception as exc:
                self.app_logger.warning(
                    f"Unable to reconcile order {order.uuid} on {order.provider_name}: {exc}"
                )
                continue

            if exchange_order is None or exchange_order.status is None:
                self._mark_reconciliation_required(order)
                continue

            try:
                self._save_orders_to_database([exchange_order])
            except Exception as exc:
                self.app_logger.warning(
                    f"Failed to persist reconciled order {order.uuid}: {exc}"
                )

    def _mark_reconciliation_required(self, order: Order) -> None:
        order.status = OrderStatus.RECONCILIATION_REQUIRED
        try:
            self._save_orders_to_database([order])
        except Exception as exc:
            self.app_logger.warning(
                f"Failed to mark order {order.uuid} as reconciliation-required: {exc}"
            )

    def open_order(
            self, ticker_symbol: str, provider_name: str, quantity: str,
            price: Decimal, trade_action: TradeAction,
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
        try:
            self.place_order(
                order.provider_name,
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
            raise RuntimeError("Error executing and/or saving order:", order) from exc

    def _cancel_order(self, open_order: Order) -> None:
        try:
            self._rest_manager.cancel_order(open_order.provider_name, open_order.uuid)
            open_order.status = OrderStatus.CANCELLED
            self._save_orders_to_database([open_order])
        except Exception as exc:
            raise RuntimeError("Unable to cancel order:", open_order) from exc

    def _get_non_terminal_orders(self) -> list[Order]:
        with self._database_manager.get_unit_of_work() as uow:
            order_repository = uow.get_repository(PostgresOrderRepository)
            return order_repository.get_non_terminal()

    def _cancel_open_orders(self):
        try:
            open_orders = [
                order for order in self._get_non_terminal_orders()
                if order.status in self.OPEN_STATUSES
            ]
        except Exception as exc:
            self.app_logger.warning(f"Unable to load open orders for cancellation: {exc}")
            return

        for order in open_orders:
            try:
                self._cancel_order(order)
            except Exception as exc:
                self.app_logger.warning(
                    f"Unable to cancel order {order.uuid} on {order.provider_name}: {exc}"
                )

    def shutdown(self):
        self._stop_order_executions()
        self.reconcile_pending_orders()
        self._cancel_open_orders()
        for asset in self._assets:
            self._websocket_manager.unsubscribe_order_update(
                exchange=asset.exchange.value,
                instrument_name=asset.ticker_symbol
            )
