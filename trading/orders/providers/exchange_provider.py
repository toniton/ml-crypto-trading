import abc
import decimal
from abc import ABC
from uuid import UUID

from entities.trade_action import TradeAction


class ExchangeProvider(ABC):
    @abc.abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abc.abstractmethod
    def get_market_price(self, ticker_symbol: str) -> decimal:
        pass

    @abc.abstractmethod
    def place_order(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: int,
            price: float,
            trade_action: TradeAction
    ):
        pass
