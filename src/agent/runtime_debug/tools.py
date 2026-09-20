from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from api.interfaces.order import Order
from src.agent.runtime_debug.models import RuntimeErrorEvent, RuntimeIncident
from src.core.interfaces.database_manager import DatabaseManager
from src.database.dao.order_dao import OrderDao
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.service import VCSService


class RuntimeDebugToolbox(ApplicationLoggingMixin):
    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            vcs: Optional[VCSService] = None,
    ):
        self._database_manager = database_manager
        self._vcs = vcs

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
            row = (
                uow.session.query(OrderDao)
                .filter(OrderDao.uuid == order_id)
                .first()
            )
            return OrderDBVSEntityMapper.map_to_entity(row) if row else None

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
