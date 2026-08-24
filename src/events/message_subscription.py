from __future__ import annotations

import queue
import threading
from typing import Optional

from src.core.interfaces.event import Event
from src.core.interfaces.event_subscription import EventSubscription


class MessageSubscription(EventSubscription):
    MAX_QUEUE_SIZE = 1000

    def __init__(self, max_size: int = MAX_QUEUE_SIZE) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=max_size)
        self._dropped = 0
        self._drop_lock = threading.Lock()
        self._closed = False

    def put(self, event: Event) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            with self._drop_lock:
                self._dropped += 1
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                pass

    def get(self, timeout: float) -> Optional[Event]:
        return self._queue.get(timeout=timeout)

    def take_dropped(self) -> int:
        with self._drop_lock:
            dropped = self._dropped
            self._dropped = 0
            return dropped

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
