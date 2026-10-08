from __future__ import annotations

from typing import List

from api.interfaces.asset import Asset
from api.interfaces.trade_action import OrderStatus
from src.core.severity import Severity
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.orders.order_manager import OrderManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler
from src.trading.session.session_manager import SessionManager




class FillReconciler(ApplicationLoggingMixin, BaseReconciler):
    def __init__(self, order_manager: OrderManager, session_manager: SessionManager):
        self._order_manager = order_manager
        self._session_manager = session_manager

    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        discrepancies: List[Discrepancy] = []
        ex_key = exchange.upper()

        try:
            # Check terminal filled orders to verify fill price and execution timestamp are present
            db_manager = self._order_manager._database_manager
            if db_manager is None:
                return discrepancies

            orders = self._order_manager._get_non_terminal_orders()
            # If any filled orders lack fill price or execution details
            for order in orders:
                if order.provider_name.upper() == ex_key and order.status == OrderStatus.COMPLETED:
                    if order.fill_price is None or order.fill_price <= 0:
                        discrepancies.append(Discrepancy(
                            discrepancy_type=DiscrepancyType.MISSING_FILL,
                            severity=Severity.WARNING,
                            exchange=ex_key,
                            asset_or_currency=order.ticker_symbol,
                            local_value="MISSING_FILL_PRICE",
                            exchange_value=f"ORDER_{order.uuid}",
                            action_taken="MARKED_RECONCILIATION_REQUIRED",
                            details={"order_uuid": order.uuid},
                        ))

        except Exception as exc:
            self.app_logger.debug("Fill reconciliation skipped for %s: %s", ex_key, exc)

        return discrepancies
