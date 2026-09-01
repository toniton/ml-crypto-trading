from __future__ import annotations

import threading
from datetime import timedelta
from typing import Optional

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.metrics.models.retention_policy import RetentionResult
from src.metrics.services.retention_engine import RetentionEngine


class RetentionScheduler(ApplicationLoggingMixin):
    def __init__(
            self,
            retention_engine: RetentionEngine,
            cleanup_interval: timedelta = timedelta(hours=1),
    ):
        self._retention_engine = retention_engine
        self._cleanup_interval = cleanup_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.app_logger.warning("Retention scheduler is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="RetentionScheduler"
        )
        self._thread.start()
        self.app_logger.info("Started retention scheduler")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.app_logger.info("Stopped retention scheduler")

    def run_once(self) -> RetentionResult:
        return self._retention_engine.run()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self._retention_engine.run()
                self.app_logger.info(f"Retention cleanup deleted {result.deleted_samples} samples")
            except Exception:  # pylint: disable=broad-except
                self.app_logger.exception("Retention cleanup failed")
            self._stop_event.wait(self._cleanup_interval.total_seconds())
