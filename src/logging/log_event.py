from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.events.message_event import MessageEvent

ASSET_SYMBOL_PATTERN = re.compile(r"\b[A-Z0-9]+_[A-Z0-9]+\b")


@dataclass
class LogEventPayload:
    domain: str = ""
    level: str = ""
    logger: str = ""
    message: str = ""
    level_no: int = logging.NOTSET
    asset: Optional[str] = None
    thread: str = ""

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "asset": self.asset,
        }


class LogEvent(MessageEvent[LogEventPayload]):
    EVENT_TYPE = "log"

    def __init__(
            self,
            payload: LogEventPayload,
            *,
            event_id: Optional[str] = None,
            timestamp: Optional[str] = None,
            metadata: Optional[dict] = None,
    ) -> None:
        super().__init__(
            self.EVENT_TYPE,
            payload,
            event_id=event_id,
            timestamp=timestamp,
            metadata=metadata,
        )


def extract_asset_symbols(message: str) -> list[str]:
    return ASSET_SYMBOL_PATTERN.findall(message)
