from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

from src.core.interfaces.event import Event
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class AutomationWorker(ApplicationLoggingMixin):
    DEFAULT_MAX_QUEUE_SIZE = 1000

    def __init__(
            self,
            handler: Callable[[Event], None],
            max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
    ):
        self._handler = handler
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.app_logger.warning("Automation worker is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="AutomationWorker"
        )
        self._thread.start()
        self.app_logger.info("Started automation worker")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                self.app_logger.warning("Automation worker failed to stop within timeout")
        self.app_logger.info("Stopped automation worker")

    def submit(self, event: Event) -> bool:
        if self._stop_event.is_set():
            return False
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            self.app_logger.warning(
                "Automation worker queue full; dropping event %s",
                event.type,
            )
            return False

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._handler(event)
            except Exception:  # pylint: disable=broad-except
                self.app_logger.exception(
                    "Automation worker failed to process %s",
                    event.type,
                )
