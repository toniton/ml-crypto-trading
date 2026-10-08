from __future__ import annotations

from typing import List, Set

from api.interfaces.asset import Asset
from src.core.severity import Severity
from src.exchange.managers.rest_manager import RestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.orders.order_manager import OrderManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler


class OrderReconciler(ApplicationLoggingMixin, BaseReconciler):
    def __init__(
            self,
            order_manager: OrderManager,
            rest_manager: RestManager,
    ):
        self._order_manager = order_manager
        self._rest_manager = rest_manager

    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        discrepancies: List[Discrepancy] = []
        ex_key = exchange.upper()

        registered_providers = set(self._rest_manager.get_registered_services())
        if exchange not in registered_providers and ex_key not in registered_providers:
            return discrepancies

        try:
            non_terminal_orders = self._order_manager._get_non_terminal_orders()
        except Exception as exc:
            self.app_logger.warning("Unable to load non-terminal orders for %s: %s", exchange, exc)
            return discrepancies

        known_local_uuids: Set[str] = set()
        for order in non_terminal_orders:
            if order.provider_name.upper() != ex_key:
                continue

            known_local_uuids.add(order.uuid)
            try:
                exchange_order = self._order_manager.get_order(order.provider_name, order.uuid)
            except Exception as exc:
                self.app_logger.warning(
                    "Unable to fetch order %s on %s: %s", order.uuid, order.provider_name, exc
                )
                continue

            if exchange_order is None or exchange_order.status is None:
                self._order_manager._mark_reconciliation_required(order)
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.ORDER_STATUS_MISMATCH,
                    severity=Severity.WARNING,
                    exchange=ex_key,
                    asset_or_currency=order.ticker_symbol,
                    local_value=str(order.status.value if order.status else "UNKNOWN"),
                    exchange_value="NOT_FOUND",
                    action_taken="MARKED_RECONCILIATION_REQUIRED",
                    details={"order_uuid": order.uuid},
                ))
                continue

            if order.status != exchange_order.status:
                prev_status = order.status
                order.status = exchange_order.status
                order.fill_price = exchange_order.fill_price
                order.fees = exchange_order.fees
                order.executed_time = exchange_order.executed_time

                try:
                    self._order_manager._save_orders_to_database([order])
                except Exception as exc:
                    self.app_logger.warning("Failed to persist reconciled order %s: %s", order.uuid, exc)

                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.ORDER_STATUS_MISMATCH,
                    severity=Severity.WARNING,
                    exchange=ex_key,
                    asset_or_currency=order.ticker_symbol,
                    local_value=str(prev_status.value if prev_status else "UNKNOWN"),
                    exchange_value=str(exchange_order.status.value if exchange_order.status else "UNKNOWN"),
                    action_taken="LOCAL_STATUS_UPDATED",
                    details={
                        "order_uuid": order.uuid,
                        "fill_price": str(order.fill_price),
                        "fees": str(order.fees),
                    },
                ))

        # Check for orphan open orders on the exchange
        try:
            exchange_open_orders = self._order_manager.get_open_orders(exchange)
            if exchange_open_orders:
                for ex_ord in exchange_open_orders:
                    if ex_ord.uuid not in known_local_uuids:
                        discrepancies.append(Discrepancy(
                            discrepancy_type=DiscrepancyType.ORPHAN_ORDER_DETECTED,
                            severity=Severity.CRITICAL,
                            exchange=ex_key,
                            asset_or_currency=ex_ord.ticker_symbol,
                            local_value="NOT_TRACKED_LOCALLY",
                            exchange_value=f"OPEN_ORDER_{ex_ord.uuid}",
                            action_taken="MANUAL_REVIEW_REQUIRED",
                            details={"order_uuid": ex_ord.uuid, "quantity": str(ex_ord.quantity), "price": str(ex_ord.price)},
                        ))
        except Exception as exc:
            self.app_logger.debug("Failed checking open orders for orphans on %s: %s", exchange, exc)

        return discrepancies
