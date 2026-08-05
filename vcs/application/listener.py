from __future__ import annotations

import json
import select
import threading
import time
from typing import Callable, Optional

from database.database_manager import DatabaseManager
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from vcs.application.events import RefChangedEvent


class RefChangeListener(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            on_event_callback: Callable[[RefChangedEvent], None],
            channel_name: str = "vcs_ref_update",
            config_vcs=None,
    ):
        self.db_manager = db_manager
        self.on_event_callback = on_event_callback
        self.channel_name = channel_name
        self.config_vcs = config_vcs
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="RefChangeListener")
        self._thread.start()
        self.app_logger.info("Started RefChangeListener background thread.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.app_logger.info("Stopped RefChangeListener background thread.")

    def _listen_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                engine = self.db_manager._create_engine()
                raw_conn = engine.raw_connection()
                # Set autocommit mode for psycopg2/psycopg3 raw connection
                if hasattr(raw_conn, "set_isolation_level"):
                    raw_conn.set_isolation_level(0)  # AUTOCOMMIT
                elif hasattr(raw_conn, "autocommit"):
                    raw_conn.autocommit = True

                cursor = raw_conn.cursor()
                cursor.execute(f"LISTEN {self.channel_name};")
                self.app_logger.info(f"Subscribed to PostgreSQL LISTEN channel '{self.channel_name}'.")
                self._reconcile()

                while not self._stop_event.is_set():
                    if select.select([raw_conn], [], [], 1.0) == ([], [], []):
                        continue

                    raw_conn.poll()
                    while raw_conn.notifies:
                        notify = raw_conn.notifies.pop(0)
                        self._handle_notify_payload(notify.payload)

                cursor.close()
                raw_conn.close()

            except Exception as e:
                if not self._stop_event.is_set():
                    self.app_logger.error(f"Error in LISTEN loop (reconnecting in 2s): {e}", exc_info=True)
                    time.sleep(2.0)

    def _reconcile(self) -> None:
        if self.config_vcs is None:
            return
        try:
            head = self.config_vcs.head("HEAD")
            event = RefChangedEvent(ref="HEAD", commit_hash=head.hash)
            self.app_logger.info(f"Reconciliation: HEAD is {head.hash[:8]}")
            self.on_event_callback(event)
        except Exception as e:
            self.app_logger.error(f"Reconciliation failed: {e}", exc_info=True)

    def _handle_notify_payload(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            ref_name = data.get("ref", "HEAD")
            commit_hash = data.get("commit", "")
            event = RefChangedEvent(ref=ref_name, commit_hash=commit_hash)
            self.app_logger.info(f"Received LISTEN event for ref '{ref_name}' pointing to {commit_hash[:8]}")
            self.on_event_callback(event)
        except Exception as e:
            self.app_logger.error(f"Failed to parse notification payload '{payload}': {e}", exc_info=True)
