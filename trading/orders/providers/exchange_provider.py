import abc
import decimal
from abc import ABC

from entities.trade_action import TradeAction


class ExchangeProvider(ABC):
    @abc.abstractmethod
    def get_provider_name(self):
        pass

    @abc.abstractmethod
    def get_market_price(self, ticker_symbol: str) -> decimal:
        pass

    @abc.abstractmethod
    def place_order(self, ticker_symbol: str, quantity: int, trade_action: TradeAction):
        pass
