from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fnmatch
import functools
import logging
import threading
from typing import Any, Callable, Iterable, Optional, Sequence, TypeVar
import uuid

from src.core.hooks.models import (
    HookContext,
    HookDispatchResult,
    HookExecutionMode,
    HookHandler,
    HookHandlerFailure,
    HookPredicate,
    HookRegistration,
    HookStage,
)

T = TypeVar("T")

TERMINAL_STAGES: frozenset[HookStage] = frozenset(
    {HookStage.COMPLETED, HookStage.FAILED, HookStage.CANCELLED}
)


class HookTracker:
    """Context manager emitting lifecycle stages for a tracked operation."""

    def __init__(
            self,
            manager: HookManager,
            hook_name: str,
            source_id: str,
            payload: Optional[dict[str, Any]] = None,
            correlation_id: Optional[str] = None,
    ) -> None:
        self._manager = manager
        self._hook_name = hook_name
        self._source_id = source_id
        self._payload: dict[str, Any] = dict(payload) if payload else {}
        self._correlation_id = correlation_id
        self._state: Optional[str] = None
        self._cancelled = False

    def transition(
            self,
            new_state: str,
            payload: Optional[dict[str, Any]] = None,
    ) -> HookDispatchResult:
        """Emits a STATE_CHANGED hook and updates the tracked state."""
        previous = self._state
        self._state = new_state
        if payload:
            self._payload.update(payload)
        return self._manager.emit(
            HookContext(
                hook_name=self._hook_name,
                stage=HookStage.STATE_CHANGED,
                source_id=self._source_id,
                state=new_state,
                previous_state=previous,
                payload=dict(self._payload),
                correlation_id=self._correlation_id,
            )
        )

    def update_payload(self, updates: dict[str, Any]) -> None:
        """Merges additional fields into the tracked operation payload."""
        self._payload.update(updates)

    def mark_cancelled(self) -> None:
        """Marks the tracked operation as cancelled on exit."""
        self._cancelled = True

    def __enter__(self) -> HookTracker:
        self._state = "STARTED"
        self._manager.emit(
            HookContext(
                hook_name=self._hook_name,
                stage=HookStage.STARTED,
                source_id=self._source_id,
                state=self._state,
                payload=dict(self._payload),
                correlation_id=self._correlation_id,
            )
        )
        return self

    def __exit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc_val: Optional[BaseException],
            _exc_tb: Any,
    ) -> None:
        previous = self._state
        if exc_type is not None:
            terminal_stage = HookStage.FAILED
            terminal_state = "FAILED"
            error_msg = str(exc_val) if exc_val is not None else exc_type.__name__
        elif self._cancelled:
            terminal_stage = HookStage.CANCELLED
            terminal_state = "CANCELLED"
            error_msg = None
        else:
            terminal_stage = HookStage.COMPLETED
            terminal_state = "COMPLETED"
            error_msg = None

        self._state = terminal_state
        self._manager.emit(
            HookContext(
                hook_name=self._hook_name,
                stage=terminal_stage,
                source_id=self._source_id,
                state=terminal_state,
                previous_state=previous,
                payload=dict(self._payload),
                error=error_msg,
                correlation_id=self._correlation_id,
            )
        )
        self._manager.emit(
            HookContext(
                hook_name=self._hook_name,
                stage=HookStage.FINALLY,
                source_id=self._source_id,
                state=terminal_state,
                previous_state=previous,
                payload=dict(self._payload),
                error=error_msg,
                correlation_id=self._correlation_id,
            )
        )


class CompositeHookBarrier:
    """Waits until every target hook has fired before invoking a callback."""

    def __init__(
            self,
            manager: HookManager,
            targets: Sequence[tuple[str, Optional[str]]],
            handler: Callable[[list[HookContext]], None],
            stages: frozenset[HookStage],
            mode: HookExecutionMode,
    ) -> None:
        self._manager = manager
        self._handler = handler
        self._mode = mode
        self._lock = threading.Lock()
        self._collected: list[Optional[HookContext]] = [None] * len(targets)
        self._remaining = len(targets)
        self._registration_ids: list[str] = []

        if not targets:
            self._dispatch_complete([])
            return

        for idx, (hook_name, source_id) in enumerate(targets):
            reg_id = manager.register_once(
                hook_name=hook_name,
                handler=self._make_slot_handler(idx),
                source_id=source_id,
                stages=stages,
                mode=HookExecutionMode.SYNC,
                name=f"when_all[{idx}]:{hook_name}",
            )
            self._registration_ids.append(reg_id)

    @property
    def registration_ids(self) -> tuple[str, ...]:
        return tuple(self._registration_ids)

    def cancel(self) -> None:
        """Unregisters any remaining pending barrier listeners."""
        for reg_id in self._registration_ids:
            self._manager.unregister(reg_id)

    def _make_slot_handler(self, slot_index: int) -> HookHandler:
        def _on_slot(context: HookContext) -> None:
            completed_contexts: Optional[list[HookContext]] = None
            with self._lock:
                if self._collected[slot_index] is not None:
                    return
                self._collected[slot_index] = context
                self._remaining -= 1
                if self._remaining == 0:
                    completed_contexts = [
                        ctx for ctx in self._collected if ctx is not None
                    ]
            if completed_contexts is not None:
                self._dispatch_complete(completed_contexts)

        return _on_slot

    def _dispatch_complete(self, contexts: list[HookContext]) -> None:
        if self._mode == HookExecutionMode.ASYNC:
            self._manager.submit_async(self._handler, contexts, "when_all")
        else:
            self._handler(contexts)


class HookManager:
    """Application-wide registry and dispatcher for operation lifecycle hooks."""

    DEFAULT_MAX_WORKERS = 4

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        self._lock = threading.RLock()
        self._registrations: dict[str, HookRegistration] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="HookWorker",
        )
        self._closed = False
        self._logger = logging.getLogger("application.HookManager")

    def register(  # pylint: disable=too-many-arguments
            self,
            hook_name: str,
            handler: HookHandler,
            *,
            stages: Optional[Iterable[HookStage]] = None,
            predicate: Optional[HookPredicate] = None,
            priority: int = 100,
            mode: HookExecutionMode = HookExecutionMode.SYNC,
            once: bool = False,
            name: str = "",
    ) -> str:
        """Registers a listener for a hook name (supports glob wildcards)."""
        stage_set = (
            frozenset(stages)
            if stages is not None
            else frozenset({HookStage.COMPLETED})
        )
        reg_id = uuid.uuid4().hex
        registration = HookRegistration(
            registration_id=reg_id,
            hook_name=hook_name,
            stages=stage_set,
            handler=handler,
            predicate=predicate,
            priority=priority,
            mode=mode,
            once=once,
            name=name or f"hook_{reg_id[:8]}",
        )
        with self._lock:
            self._registrations[reg_id] = registration
        return reg_id

    def register_once(  # pylint: disable=too-many-arguments
            self,
            hook_name: str,
            handler: HookHandler,
            *,
            source_id: Optional[str] = None,
            stages: Optional[Iterable[HookStage]] = None,
            predicate: Optional[HookPredicate] = None,
            priority: int = 100,
            mode: HookExecutionMode = HookExecutionMode.SYNC,
            name: str = "",
    ) -> str:
        """Registers a one-shot listener, optionally scoped to a specific source_id."""

        def _combined_predicate(ctx: HookContext) -> bool:
            if source_id is not None and ctx.source_id != source_id:
                return False
            if predicate is not None:
                return predicate(ctx)
            return True

        return self.register(
            hook_name=hook_name,
            handler=handler,
            stages=stages,
            predicate=_combined_predicate,
            priority=priority,
            mode=mode,
            once=True,
            name=name,
        )

    def unregister(self, registration_id: str) -> bool:
        """Removes a registered listener by ID."""
        with self._lock:
            return self._registrations.pop(registration_id, None) is not None

    def listener_count(self, hook_name: Optional[str] = None) -> int:
        """Returns the number of active listeners, optionally filtered by hook name."""
        with self._lock:
            if hook_name is None:
                return len(self._registrations)
            return sum(
                1
                for reg in self._registrations.values()
                if self._matches_name(reg.hook_name, hook_name)
            )

    def emit(self, context: HookContext) -> HookDispatchResult:
        """Dispatches a HookContext to all matching listeners in priority order."""
        matched: list[HookRegistration] = []
        with self._lock:
            candidates = sorted(
                self._registrations.values(),
                key=lambda reg: (reg.priority, reg.registration_id),
            )
            for reg in candidates:
                if context.stage not in reg.stages:
                    continue
                if not self._matches_name(reg.hook_name, context.hook_name):
                    continue
                if reg.predicate is not None and not self._safe_predicate(reg, context):
                    continue
                matched.append(reg)
                if reg.once:
                    self._registrations.pop(reg.registration_id, None)

        sync_executed = 0
        async_submitted = 0
        failures: list[HookHandlerFailure] = []

        for reg in matched:
            if reg.mode == HookExecutionMode.ASYNC:
                if not self._closed:
                    self._executor.submit(self._run_async_handler, reg, context)
                    async_submitted += 1
                continue

            sync_executed += 1
            failure = self._run_sync_handler(reg, context)
            if failure is not None:
                failures.append(failure)

        return HookDispatchResult(
            hook_name=context.hook_name,
            stage=context.stage,
            matched_count=len(matched),
            sync_executed=sync_executed,
            async_submitted=async_submitted,
            failures=tuple(failures),
        )

    def track(
            self,
            hook_name: str,
            source_id: str,
            payload: Optional[dict[str, Any]] = None,
            correlation_id: Optional[str] = None,
    ) -> HookTracker:
        """Returns a context manager that tracks an operation's lifecycle stages."""
        return HookTracker(
            manager=self,
            hook_name=hook_name,
            source_id=source_id,
            payload=payload,
            correlation_id=correlation_id,
        )

    def wrap(
            self,
            hook_name: str,
            func: Callable[..., T],
            *,
            source_id_factory: Optional[Callable[..., str]] = None,
            payload_factory: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> Callable[..., T]:
        """Wraps a callable so invocations emit STARTED, COMPLETED/FAILED, and FINALLY."""

        @functools.wraps(func)
        def _wrapped(*args: Any, **kwargs: Any) -> T:
            source_id = (
                source_id_factory(*args, **kwargs)
                if source_id_factory is not None
                else uuid.uuid4().hex
            )
            payload = (
                payload_factory(*args, **kwargs)
                if payload_factory is not None
                else {}
            )
            with self.track(hook_name, source_id=source_id, payload=payload) as tracker:
                result = func(*args, **kwargs)
                tracker.update_payload({"result": result})
                return result

        return _wrapped

    def when_all(
            self,
            targets: Sequence[tuple[str, Optional[str]]],
            handler: Callable[[list[HookContext]], None],
            *,
            stages: Optional[Iterable[HookStage]] = None,
            mode: HookExecutionMode = HookExecutionMode.SYNC,
    ) -> CompositeHookBarrier:
        """Invokes handler once every target (hook_name, source_id) reaches a stage."""
        stage_set = (
            frozenset(stages)
            if stages is not None
            else frozenset({HookStage.COMPLETED})
        )
        return CompositeHookBarrier(
            manager=self,
            targets=targets,
            handler=handler,
            stages=stage_set,
            mode=mode,
        )

    def submit_async(
            self,
            callback: Callable[[Any], None],
            arg: Any,
            label: str,
    ) -> None:
        """Runs an arbitrary callback on the bounded hook worker pool."""
        if self._closed:
            return

        def _runner() -> None:
            try:
                callback(arg)
            except Exception:  # pylint: disable=broad-except
                self._logger.exception("Async hook callback '%s' failed", label)

        self._executor.submit(_runner)

    def close(self, wait: bool = True) -> None:
        """Clears registrations and shuts down the async worker pool."""
        with self._lock:
            self._closed = True
            self._registrations.clear()
        self._executor.shutdown(wait=wait)

    def _safe_predicate(
            self,
            registration: HookRegistration,
            context: HookContext,
    ) -> bool:
        assert registration.predicate is not None
        try:
            return bool(registration.predicate(context))
        except Exception:  # pylint: disable=broad-except
            self._logger.exception(
                "Hook predicate failed for '%s' (%s)",
                registration.name,
                registration.hook_name,
            )
            return False

    def _run_sync_handler(
            self,
            registration: HookRegistration,
            context: HookContext,
    ) -> Optional[HookHandlerFailure]:
        try:
            registration.handler(context)
            return None
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.exception(
                "Sync hook handler '%s' failed for %s:%s",
                registration.name,
                context.hook_name,
                context.stage.value,
            )
            return HookHandlerFailure(
                registration_id=registration.registration_id,
                handler_name=registration.name,
                error=str(exc),
            )

    def _run_async_handler(
            self,
            registration: HookRegistration,
            context: HookContext,
    ) -> None:
        try:
            registration.handler(context)
        except Exception:  # pylint: disable=broad-except
            self._logger.exception(
                "Async hook handler '%s' failed for %s:%s",
                registration.name,
                context.hook_name,
                context.stage.value,
            )

    @staticmethod
    def _matches_name(pattern: str, hook_name: str) -> bool:
        if pattern == hook_name:
            return True
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatchcase(hook_name, pattern)
        return False
