from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, TypeVar, Generic
from pydantic import BaseModel

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.core.interfaces.mapper import Mapper

T = TypeVar('T', bound=BaseModel)
R = TypeVar('R')


@dataclass(frozen=True)
class Endpoint:
    path: str
    private: bool
    mapper: Optional[Mapper] = None


class ExchangeRestBuilder(abc.ABC, Generic[T, R]):
    def __init__(self):
        self._mapper: Mapper[T, R] | None = None

    @abc.abstractmethod
    def market_data(self, ticker_symbol: str) -> 'ExchangeRestBuilder[T, MarketData]':
        raise NotImplementedError()

    @abc.abstractmethod
    def candles(self, ticker_symbol: str, timeframe) -> 'ExchangeRestBuilder[T, list[Candle]]':
        raise NotImplementedError()

    @abc.abstractmethod
    def account_balance(self) -> 'ExchangeRestBuilder[T, list[AccountBalance]]':
        raise NotImplementedError()

    @abc.abstractmethod
    def account_fees(self) -> 'ExchangeRestBuilder[T, Fees]':
        raise NotImplementedError()

    @abc.abstractmethod
    def instrument_fees(self, ticker_symbol: str) -> 'ExchangeRestBuilder[T, Fees]':
        raise NotImplementedError()

    @abc.abstractmethod
    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action
    ) -> 'ExchangeRestBuilder[T, None]':
        raise NotImplementedError()

    @abc.abstractmethod
    def get_order(self, uuid: str) -> 'ExchangeRestBuilder[T, Order]':
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_order(self, uuid: str) -> 'ExchangeRestBuilder[T, None]':
        raise NotImplementedError()
