from __future__ import annotations

import abc
from abc import ABC
from typing import Callable
from uuid import UUID

import websocket

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from enum import Enum


class ExchangeProvidersEnum(Enum):
    CRYPTO_DOT_COM = "CRYPTO_DOT_COM"
    BACKTEST = "BACKTEST"


class ExchangeProvider(ABC):
    @abc.abstractmethod
    def get_provider_name(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_market_subscription_data(self, ticker_symbol: str) -> dict | None:
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
            uuid: UUID,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_websocket_client(
            self, on_open: Callable, on_message: Callable,
            on_error: Callable,
            on_close: Callable
    ) -> websocket.WebSocketApp:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_candle(
            self,
            ticker_symbol: str,
            timeframe: Timeframe
    ) -> list[Candle]:
        raise NotImplementedError()
