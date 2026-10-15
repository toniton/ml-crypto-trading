from __future__ import annotations

import threading
from datetime import timedelta
from typing import Optional

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.retention.manager import RetentionManager


class RetentionScheduler(ApplicationLoggingMixin):
    def __init__(self, manager: RetentionManager, interval: Optional[timedelta] = None):
        self._manager = manager
        self._interval = interval or manager.schedule_interval()
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

    def run_once(self) -> Optional[dict]:
        if not self._manager.config.enabled:
            return None
        return self._manager.execute(actor="retention-scheduler")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self.run_once()
                if result is not None:
                    self.app_logger.info(
                        "Retention run %s finished with status %s",
                        result.get("run_id"),
                        result.get("status"),
                    )
            except Exception:  # pylint: disable=broad-except
                self.app_logger.exception("Retention run failed")
            self._stop_event.wait(self._interval.total_seconds())
