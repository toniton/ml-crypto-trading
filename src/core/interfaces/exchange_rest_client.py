from __future__ import annotations

import abc
from abc import ABC

from enum import Enum

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction


class ExchangeProvidersEnum(Enum):
    CRYPTO_DOT_COM = "CRYPTO_DOT_COM"
    BACKTEST = "BACKTEST"


class ExchangeRestClient(ABC):
    @abc.abstractmethod
    def get_provider_name(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_market_data(self, ticker_symbol: str) -> MarketData:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_account_balance(self) -> list[AccountBalance]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_account_fees(self) -> Fees:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_instrument_fees(self, ticker_symbol: str) -> Fees:
        raise NotImplementedError()

    @abc.abstractmethod
    def place_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_candle(
            self,
            ticker_symbol: str,
            timeframe: Timeframe
    ) -> list[Candle]:
        raise NotImplementedError()
