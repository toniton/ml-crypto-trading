import abc
from dataclasses import dataclass
from typing import Optional, Callable, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)
R = TypeVar('R')


@dataclass(frozen=True)
class Endpoint:
    path: str
    response_dto: type[BaseModel]
    private: bool


class ExchangeRequestBuilder(abc.ABC, Generic[T]):

    @abc.abstractmethod
    def market_data(self, ticker_symbol: str) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def candles(self, ticker_symbol: str, timeframe) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def account_balance(self) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def account_fees(self) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def instrument_fees(self, ticker_symbol: str) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action
    ) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_order(self, uuid: str) -> 'ExchangeRequestBuilder':
        raise NotImplementedError()

    @abc.abstractmethod
    def execute(self, mapper: Optional[Callable[[T], R]] = None):
        raise NotImplementedError()
