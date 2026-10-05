from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from api.interfaces.order import Order
from src.agent.runtime_debug.models import RuntimeErrorEvent, RuntimeIncident
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.health.health_monitor import HealthMonitor
from src.vcs.application.service import VCSService


class RuntimeDebugToolbox(ApplicationLoggingMixin):
    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            vcs: Optional[VCSService] = None,
            health_monitor: Optional[HealthMonitor] = None,
    ):
        self._database_manager = database_manager
        self._vcs = vcs
        self._health_monitor = health_monitor

    def get_trading_health_snapshot(self) -> Optional[dict[str, Any]]:
        if not self._health_monitor:
            return None
        snapshot = self._health_monitor.snapshot
        return {
            "state": snapshot.state.value,
            "version": snapshot.version,
            "effective_permissions": [p.value for p in snapshot.effective_permissions],
            "active_conditions": [
                {
                    "condition": c.condition.value,
                    "scope_type": c.scope.scope_type.value,
                    "scope_identifier": c.scope.identifier,
                    "severity": c.severity.value,
                    "measured_value": str(c.measured_value) if c.measured_value is not None else None,
                    "threshold": str(c.threshold) if c.threshold is not None else None,
                    "consecutive_healthy_checks": c.consecutive_healthy_checks,
                    "first_detected_at": c.first_detected_at.isoformat(),
                    "last_observed_at": c.last_observed_at.isoformat(),
                }
                for c in snapshot.active_conditions
            ],
            "updated_at": snapshot.updated_at.isoformat(),
        }

    def get_incident(self, incident_id: str) -> Optional[RuntimeIncident]:
        if not self._database_manager:
            return None
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            return repo.get(incident_id)

    def get_error_events(self, incident_id: str, limit: int = 50) -> list[RuntimeErrorEvent]:
        if not self._database_manager:
            return []
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            return repo.get_error_events(UUID(incident_id), limit=limit)

    def get_recent_errors(
            self,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 10,
    ) -> list[RuntimeErrorEvent]:
        if not self._database_manager:
            return []
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            return repo.get_recent_error_events(asset=asset, exchange=exchange, limit=limit)

    def get_order(self, order_id: str) -> Optional[Order]:
        if not self._database_manager:
            return None
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresOrderRepository)
            return repo.get(order_id)

    def get_last_successful_order_commit(self, asset: str) -> Optional[str]:
        if not self._database_manager:
            return None
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresOrderRepository)
            last_order = repo.get_last_completed_by_ticker(asset)
            if last_order and last_order.commit_hash and last_order.commit_hash != "HEAD":
                return last_order.commit_hash
        return None

    def get_configuration_at_commit(self, commit_hash: str) -> dict[str, Any]:
        if not self._vcs:
            return {}
        try:
            return self._vcs.checkout(commit_hash)
        except Exception as exc:
            self.app_logger.warning(f"Unable to checkout commit {commit_hash}: {exc}")
            return {}

    def get_configuration_diff(self, commit_hash_a: str, commit_hash_b: str) -> dict[str, Any]:
        if not self._vcs:
            return {}
        try:
            config_a = self.get_configuration_at_commit(commit_hash_a)
            config_b = self.get_configuration_at_commit(commit_hash_b)
            return {
                "commit_a": commit_hash_a,
                "commit_b": commit_hash_b,
                "config_a": config_a,
                "config_b": config_b,
            }
        except Exception as exc:
            self.app_logger.warning(f"Unable to compute config diff: {exc}")
            return {}

    def get_exchange_instrument_metadata(self, exchange: str, symbol: str) -> dict[str, Any]:
        # Exchange rule catalog for known symbols
        normalized_symbol = symbol.upper().replace("/", "_").replace("-", "_")
        provider = (exchange or "").upper()

        if provider == "CRYPTO_DOT_COM":
            if "BTC" in normalized_symbol:
                return {
                    "exchange": "CRYPTO_DOT_COM",
                    "symbol": normalized_symbol,
                    "quantity_precision": 4,
                    "min_quantity": "0.0001",
                    "quantity_step": "0.0001",
                    "price_precision": 2,
                    "min_price": "0.01",
                }
            if "ETH" in normalized_symbol:
                return {
                    "exchange": "CRYPTO_DOT_COM",
                    "symbol": normalized_symbol,
                    "quantity_precision": 3,
                    "min_quantity": "0.001",
                    "quantity_step": "0.001",
                    "price_precision": 2,
                    "min_price": "0.01",
                }

        return {
            "exchange": provider,
            "symbol": normalized_symbol,
            "quantity_precision": 4,
            "min_quantity": "0.0001",
            "quantity_step": "0.0001",
            "price_precision": 2,
            "min_price": "0.01",
        }
