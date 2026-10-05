from __future__ import annotations

import abc
from datetime import datetime
from typing import List, Optional

from src.database.repositories.base_repository import BaseRepository
from src.trading.decision.trading_decision import TradingDecision


class TradingDecisionRepository(BaseRepository[TradingDecision]):
    @abc.abstractmethod
    def get_by_order_id(self, order_id: str) -> Optional[TradingDecision]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_ticker_symbol(
            self, ticker_symbol: str, limit: int = 50
    ) -> List[TradingDecision]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_commit_hash(self, commit_hash: str) -> List[TradingDecision]:
        raise NotImplementedError()

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    @abc.abstractmethod
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
        raise NotImplementedError()
