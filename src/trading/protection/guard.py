import abc

from api.interfaces.trading_context import TradingContext
from src.configuration.guard_config import GuardConfig
from src.entities.asset import Asset


class Guard(abc.ABC, metaclass=abc.ABCMeta):
    def __init__(self, config: GuardConfig):
        self.config = config

    def can_trade(self, trading_context: TradingContext) -> bool:
        pass

    @staticmethod
    @abc.abstractmethod
    def is_enabled(asset: Asset):
        pass
