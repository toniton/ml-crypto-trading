import abc

from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.asset import Asset
from src.configuration.guard_config import GuardConfig


class Guard(abc.ABC, metaclass=abc.ABCMeta):
    def __init__(self, config: GuardConfig):
        self.config = config

    def can_trade(self, trade_action: TradeAction, trading_context: TradingContext) -> bool:
        pass

    @staticmethod
    @abc.abstractmethod
    def is_enabled(asset: Asset):
        pass
