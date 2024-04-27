from __future__ import annotations

from abc import ABC

from api.interfaces.trading_strategy import TradingStrategy


class RuleBasedTradingStrategy(TradingStrategy, ABC):
    def __init__(self):
        super().__init__()
