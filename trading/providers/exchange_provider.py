import abc
import decimal
from abc import ABC
from typing import Any, Callable
from uuid import UUID

import websocket

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

    @abc.abstractmethod
    def get_websocket_client(
            self, on_open: Callable, on_message: Callable,
            on_close: Callable
    ) -> websocket.WebSocketApp:
        pass
