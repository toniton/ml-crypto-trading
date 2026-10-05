from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.trading_decision_repository import (
    TradingDecisionRepository,
)
from src.database.repositories.providers.postgres_trading_decision_repository import (
    PostgresTradingDecisionRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.decision.trading_decision import TradingDecision


class DecisionManager(ApplicationLoggingMixin):
    """Manages recording, query lookup, and lifecycle retrieval of trading decisions."""

    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            repository: Optional[TradingDecisionRepository] = None,
    ):
        self._database_manager = database_manager
        self._repository = repository

    def record_decision(self, decision: TradingDecision) -> None:
        if self._repository is not None:
            self._repository.save(decision)
            return

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                repo.save(decision)

    def get_decision(self, decision_id: str) -> Optional[TradingDecision]:
        if self._repository is not None:
            return self._repository.get(decision_id)

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                return repo.get(decision_id)
        return None

    def get_decision_by_order_id(self, order_id: str) -> Optional[TradingDecision]:
        if self._repository is not None:
            return self._repository.get_by_order_id(order_id)

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                return repo.get_by_order_id(order_id)
        return None

    def get_decisions_by_symbol(self, ticker_symbol: str, limit: int = 50) -> List[TradingDecision]:
        if self._repository is not None:
            return self._repository.get_by_ticker_symbol(ticker_symbol, limit=limit)

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                return repo.get_by_ticker_symbol(ticker_symbol, limit=limit)
        return []

    def get_decisions_by_commit(self, commit_hash: str) -> List[TradingDecision]:
        if self._repository is not None:
            return self._repository.get_by_commit_hash(commit_hash)

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                return repo.get_by_commit_hash(commit_hash)
        return []

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def list_decisions(
            self,
            ticker_symbol: Optional[str] = None,
            exchange: Optional[str] = None,
            status: Optional[str] = None,
            since: Optional[datetime] = None,
            until: Optional[datetime] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[TradingDecision]:
        if self._repository is not None:
            return self._repository.list_decisions(
                ticker_symbol=ticker_symbol,
                exchange=exchange,
                status=status,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
            )

        if self._database_manager is not None:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                return repo.list_decisions(
                    ticker_symbol=ticker_symbol,
                    exchange=exchange,
                    status=status,
                    since=since,
                    until=until,
                    limit=limit,
                    offset=offset,
                )
        return []
