from __future__ import annotations

import abc

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext


class TradingStrategy(abc.ABC, metaclass=abc.ABCMeta):
    def __init__(self, ticker_symbols: set[str] | list[str] | None = None):
        self.action: TradeAction | None = None
        self.ticker_symbols: set[str] | None = set(ticker_symbols) if ticker_symbols is not None else None

    @property
    def name(self) -> str:
        return type(self).__name__

    @abc.abstractmethod
    def get_quorum(
            self,
            trade_action: TradeAction, ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        raise NotImplementedError()
