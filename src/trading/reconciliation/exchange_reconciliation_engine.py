from __future__ import annotations

import threading
import time
import uuid
from typing import List, Optional, Set

from api.interfaces.asset import Asset
from src.core.interfaces.event_bus import EventBus
from src.exchange.managers.rest_manager import RestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.metrics.collectors.order_lifecycle_collector import OrderLifecycleCollector
from src.trading.accounts.account_manager import AccountManager
from src.trading.events.domain_events import (
    ReconciliationCompletedEvent,
    ReconciliationDiscrepancyEvent,
)
from src.trading.fees.fees_manager import FeesManager
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
)
from src.trading.reconciliation.models.reconciliation_report import (
    ReconciliationReport,
)
from src.trading.reconciliation.reconcilers.balance_reconciler import (
    BalanceReconciler,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler
from src.trading.reconciliation.reconcilers.fee_reconciler import FeeReconciler
from src.trading.reconciliation.reconcilers.fill_reconciler import FillReconciler
from src.trading.reconciliation.reconcilers.order_reconciler import (
    OrderReconciler,
)
from src.trading.reconciliation.reconcilers.position_reconciler import (
    PositionReconciler,
)
from src.trading.session.session_manager import SessionManager


class ExchangeReconciliationEngine(ApplicationLoggingMixin):
    RECONCILE_INTERVAL_SECONDS = 30.0

    def __init__(
            self,
            reconcilers: List[BaseReconciler],
            assets: List[Asset],
            event_bus: Optional[EventBus] = None,
            protection_manager: Optional[ProtectionManager] = None,
            order_lifecycle_collector: Optional[OrderLifecycleCollector] = None,
            auto_pause_on_critical: bool = True,
    ):
        self._reconcilers = reconcilers
        self._assets = assets
        self._event_bus = event_bus
        self._protection_manager = protection_manager
        self._order_lifecycle_collector = order_lifecycle_collector
        self._auto_pause_on_critical = auto_pause_on_critical

        self._active_discrepancies: List[Discrepancy] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def create(
            cls,
            account_manager: AccountManager,
            order_manager: OrderManager,
            session_manager: SessionManager,
            fees_manager: FeesManager,
            rest_manager: RestManager,
            assets: List[Asset],
            event_bus: Optional[EventBus] = None,
            protection_manager: Optional[ProtectionManager] = None,
            order_lifecycle_collector: Optional[OrderLifecycleCollector] = None,
            auto_pause_on_critical: bool = True,
    ) -> ExchangeReconciliationEngine:
        reconcilers: List[BaseReconciler] = [
            BalanceReconciler(account_manager, rest_manager, session_manager),
            OrderReconciler(order_manager, rest_manager),
            PositionReconciler(session_manager, account_manager),
            FeeReconciler(fees_manager),
            FillReconciler(order_manager, session_manager),
        ]
        return cls(
            reconcilers=reconcilers,
            assets=assets,
            event_bus=event_bus,
            protection_manager=protection_manager,
            order_lifecycle_collector=order_lifecycle_collector,
            auto_pause_on_critical=auto_pause_on_critical,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ExchangeReconciliationEngine",
        )
        self._thread.start()
        self.app_logger.info("Exchange reconciliation engine started")

    def stop(self) -> None:
        self._stop_event.set()
        self._trigger_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.RECONCILE_INTERVAL_SECONDS + 5)
        self.app_logger.info("Exchange reconciliation engine stopped")

    def trigger(self) -> None:
        self._trigger_event.set()

    def has_critical_discrepancy(
            self,
            exchange: Optional[str] = None,
            symbol: Optional[str] = None,
    ) -> bool:
        with self._lock:
            for d in self._active_discrepancies:
                if not d.is_critical:
                    continue
                if exchange and d.exchange.upper() != exchange.upper():
                    continue
                if symbol and d.asset_or_currency.upper() != symbol.upper():
                    continue
                return True
        return False

    def get_active_discrepancies(self) -> List[Discrepancy]:
        with self._lock:
            return list(self._active_discrepancies)

    def clear_discrepancies(self) -> None:
        with self._lock:
            self._active_discrepancies.clear()
        if self._protection_manager and self._protection_manager.is_paused:
            self._protection_manager.resume_trading()
            self.app_logger.info("Cleared reconciliation discrepancies; resumed trading.")

    def update_assets(self, assets: List[Asset]) -> None:
        self._assets = assets

    def reconcile_all(self) -> List[ReconciliationReport]:
        reports: List[ReconciliationReport] = []
        exchanges: Set[str] = {asset.exchange.value for asset in self._assets}

        for exchange in exchanges:
            cycle_id = str(uuid.uuid4())
            started_at = time.time()
            report_discrepancies: List[Discrepancy] = []

            for reconciler in self._reconcilers:
                try:
                    disc = reconciler.reconcile(exchange, self._assets)
                    report_discrepancies.extend(disc)
                except Exception as exc:
                    self.app_logger.error(
                        "Error running %s on %s: %s",
                        reconciler.__class__.__name__,
                        exchange,
                        exc,
                        exc_info=True,
                    )

            finished_at = time.time()
            report = ReconciliationReport(
                cycle_id=cycle_id,
                exchange=exchange,
                started_at=started_at,
                finished_at=finished_at,
                discrepancies=report_discrepancies,
            )
            reports.append(report)

            with self._lock:
                # Update active discrepancies for this exchange
                self._active_discrepancies = [
                    d for d in self._active_discrepancies
                    if d.exchange.upper() != exchange.upper()
                ] + report_discrepancies

            # Handle policy actions
            if report.has_critical:
                if self._auto_pause_on_critical and self._protection_manager:
                    self._protection_manager.pause_trading(
                        f"Critical reconciliation discrepancy detected on {exchange}"
                    )
            elif not self.has_critical_discrepancy():
                if self._auto_pause_on_critical and self._protection_manager and self._protection_manager.is_paused:
                    self._protection_manager.resume_trading()
                    self.app_logger.info(
                        "Reconciliation cycle clean across exchanges; auto-resumed trading."
                    )

            # Publish events
            if self._event_bus:
                for disc in report_discrepancies:
                    self._event_bus.publish(
                        ReconciliationDiscrepancyEvent(
                            discrepancy_type=disc.discrepancy_type.value,
                            severity=disc.severity.value,
                            exchange=disc.exchange,
                            asset_or_currency=disc.asset_or_currency,
                            local_value=disc.local_value,
                            exchange_value=disc.exchange_value,
                            difference=disc.difference,
                            action_taken=disc.action_taken,
                            details=disc.details,
                        )
                    )

                self._event_bus.publish(
                    ReconciliationCompletedEvent(
                        cycle_id=cycle_id,
                        exchange=exchange,
                        duration_ms=report.duration_ms,
                        discrepancies_count=report.total_count,
                        critical_count=len(report.critical_discrepancies),
                        actions_taken=report.actions_taken,
                    )
                )

        if self._order_lifecycle_collector:
            try:
                self._order_lifecycle_collector.collect_and_record()
            except Exception as exc:
                self.app_logger.warning("Order lifecycle metric collection failed: %s", exc)

        return reports

    def reconcile_pending_orders(self) -> None:
        self.reconcile_all()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._trigger_event.wait(timeout=self.RECONCILE_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            self._trigger_event.clear()
            try:
                self.reconcile_all()
            except Exception as exc:
                self.app_logger.warning("Reconciliation cycle failed: %s", exc)

        self.app_logger.info("Exchange reconciliation engine thread exiting")
