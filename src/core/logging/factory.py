import logging
from typing import Optional

from src.core.logging.domain import LogDomain
from src.core.logging.manager import LoggingManager


class LoggingFactory:
    @staticmethod
    def get_application_logger(name: str) -> logging.Logger:
        return LoggingManager.get_instance().get_logger(LogDomain.APPLICATION, name)

    @staticmethod
    def get_trading_logger(name: str) -> logging.Logger:
        return LoggingManager.get_instance().get_logger(LogDomain.TRADING, name)

    @staticmethod
    def get_audit_logger(asset: Optional[str] = None) -> logging.Logger:
        return LoggingManager.get_instance().get_logger(LogDomain.AUDIT, asset=asset)
