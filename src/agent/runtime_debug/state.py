from __future__ import annotations

from typing import Any, Optional, TypedDict

from src.agent.runtime_debug.models import (
    ConfidenceLevel,
    DebugDiagnosis,
    DebugSuggestion,
    ErrorCategory,
    Evidence,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.core.interfaces.llm_adapter import ChatTurn


class RuntimeDebugPresentation:
    def __init__(self, blocks: list[dict[str, Any]]):
        self.blocks = blocks


class RuntimeDebugState(TypedDict, total=False):
    user_prompt: str
    history: list[ChatTurn]
    incident_id: Optional[str]
    error_event: Optional[RuntimeErrorEvent]
    incident: Optional[RuntimeIncident]
    context: dict[str, Any]
    classification: Optional[ErrorCategory]
    evidence: list[Evidence]
    diagnosis: Optional[DebugDiagnosis]
    suggestion: Optional[DebugSuggestion]
    confidence: ConfidenceLevel
    investigation_attempts: int
    presentation: Optional[RuntimeDebugPresentation]
