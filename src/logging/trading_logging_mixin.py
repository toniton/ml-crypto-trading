from __future__ import annotations
import logging
from src.logging.factory import LoggingFactory


class TradingLoggingMixin:
    @property
    def trading_logger(self) -> logging.Logger:
        return LoggingFactory.get_trading_logger(self.__class__.__name__)
