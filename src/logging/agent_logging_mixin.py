from __future__ import annotations
import logging
from src.logging.factory import LoggingFactory


class AgentLoggingMixin:
    @property
    def agent_logger(self) -> logging.Logger:
        return LoggingFactory.get_agent_logger(self.__class__.__name__)
