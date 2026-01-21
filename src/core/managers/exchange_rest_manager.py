from __future__ import annotations

import abc
from abc import ABC

from enum import Enum

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction


class ExchangeProvidersEnum(Enum):
    CRYPTO_DOT_COM = "CRYPTO_DOT_COM"
    BACKTEST = "BACKTEST"


class ExchangeRestManager(ABC):
    @abc.abstractmethod
    def get_market_data(self, exchange: str, ticker_symbol: str) -> MarketData:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_account_balance(self, exchange: str) -> list[AccountBalance]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_account_fees(self, exchange: str) -> Fees:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_instrument_fees(self, exchange: str, ticker_symbol: str) -> Fees:
        raise NotImplementedError()

    @abc.abstractmethod
    def place_order(
            self, exchange: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_order(
            self, exchange: str,
            uuid: str
    ) -> Order:
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_order(
            self, exchange: str,
            uuid: str
    ) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_candles(
            self, exchange: str,
            ticker_symbol: str,
            timeframe: Timeframe
    ) -> list[Candle]:
        raise NotImplementedError()
