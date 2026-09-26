from __future__ import annotations

import abc
from datetime import datetime
from typing import Optional

from api.interfaces.trade import Trade
from src.database.repositories.base_repository import BaseRepository


class TradeRepository(BaseRepository[Trade]):

    @abc.abstractmethod
    def get_by_ticker_symbol(self, ticker_symbol: str) -> list[Trade]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_exit_range(
            self, ticker_symbol: Optional[str], start: datetime, end: datetime
    ) -> list[Trade]:
        raise NotImplementedError()
