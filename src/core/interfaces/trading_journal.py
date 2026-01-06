from abc import ABC, abstractmethod
from typing import List
from api.interfaces.order import Order


class TradingJournal(ABC):
    @abstractmethod
    def record_fill(self, order: Order) -> None:
        pass

    @abstractmethod
    def entries(self, ticker_symbol: str = None) -> List[Order]:
        pass
