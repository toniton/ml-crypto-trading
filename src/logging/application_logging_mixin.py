from __future__ import annotations
import logging
from src.logging.factory import LoggingFactory


class ApplicationLoggingMixin:
    @property
    def app_logger(self) -> logging.Logger:
        return LoggingFactory.get_application_logger(self.__class__.__name__)
