from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.core.interfaces.event_bus import EventBus
from src.logging.log_event import LogEvent, LogEventPayload, extract_asset_symbols


class EventBusLogHandler(logging.Handler):
    def __init__(self, bus: EventBus, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bus.publish(self._to_event(record))
        except Exception:  # pylint: disable=broad-except
            self.handleError(record)

    def _to_event(self, record: logging.LogRecord) -> LogEvent:
        message = record.getMessage()
        payload = LogEventPayload(
            domain=record.name.split(".")[0],
            level=record.levelname,
            level_no=record.levelno,
            logger=record.name,
            message=message,
            asset=self._resolve_asset(record, message),
            thread=record.threadName,
        )
        return LogEvent(
            payload,
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            metadata=dict(getattr(record, "metadata", None) or {}),
        )

    @staticmethod
    def _resolve_asset(record: logging.LogRecord, message: str) -> Optional[str]:
        explicit = getattr(record, "asset", None)
        if explicit:
            return explicit
        symbols = extract_asset_symbols(message)
        if len(symbols) == 1:
            return symbols[0]
        return None
