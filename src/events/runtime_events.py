from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.events.trading_event import TradingEvent


@dataclass
class RuntimeErrorCapturedEvent(TradingEvent):
    event_payload: dict[str, Any] = None


@dataclass
class RuntimeIncidentCreatedEvent(TradingEvent):
    incident_payload: dict[str, Any] = None


@dataclass
class RuntimeIncidentUpdatedEvent(TradingEvent):
    incident_payload: dict[str, Any] = None


@dataclass
class DebugSuggestionCreatedEvent(TradingEvent):
    incident_id: str = ""
    suggestion_payload: dict[str, Any] = None
