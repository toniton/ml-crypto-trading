from __future__ import annotations

import abc

from entities.market_data import MarketData
from entities.trade_action import TradeAction
from trading.context.trading_context import TradingContext


class TradingStrategy(metaclass=abc.ABCMeta):
    def __init__(self):
        self.type: TradeAction | None = None

    @abc.abstractmethod
    def get_quorum(
        self,
        trade_action: TradeAction, ticker_symbol: str,
        trading_context: TradingContext,
        market_data: MarketData
    ):
        raise NotImplementedError()
