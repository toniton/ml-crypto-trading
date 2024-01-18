import abc
import decimal
from abc import ABC
from typing import Callable
from uuid import UUID

import websocket

from entities.trade_action import TradeAction


class ExchangeProvider(ABC):
    @abc.abstractmethod
    def get_provider_name(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_market_data(self, ticker_symbol: str) -> decimal:
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
            on_close: Callable
    ) -> websocket.WebSocketApp:
        raise NotImplementedError()
