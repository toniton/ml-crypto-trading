from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class HookStage(str, Enum):
    """Lifecycle stages emitted by instrumented operations."""

    STARTED = "STARTED"
    STATE_CHANGED = "STATE_CHANGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    FINALLY = "FINALLY"


class HookExecutionMode(str, Enum):
    """Controls whether a hook listener executes inline or on the worker pool."""

    SYNC = "SYNC"
    ASYNC = "ASYNC"


@dataclass(frozen=True)
class HookContext:
    """Immutable snapshot passed to hook listeners."""

    hook_name: str
    stage: HookStage
    source_id: str
    state: Optional[str] = None
    previous_state: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


HookHandler = Callable[[HookContext], None]
HookPredicate = Callable[[HookContext], bool]


@dataclass(frozen=True)
class HookRegistration:
    """Metadata describing a registered hook listener."""

    registration_id: str
    hook_name: str
    stages: frozenset[HookStage]
    handler: HookHandler
    predicate: Optional[HookPredicate] = None
    priority: int = 100
    mode: HookExecutionMode = HookExecutionMode.SYNC
    once: bool = False
    name: str = ""


@dataclass(frozen=True)
class HookHandlerFailure:
    """Records an isolated exception raised by a hook listener."""

    registration_id: str
    handler_name: str
    error: str


@dataclass(frozen=True)
class HookDispatchResult:
    """Summary of dispatching a HookContext to matching listeners."""

    hook_name: str
    stage: HookStage
    matched_count: int
    sync_executed: int
    async_submitted: int
    failures: tuple[HookHandlerFailure, ...] = ()
