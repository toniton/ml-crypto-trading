from threading import Lock
from typing import List


class BacktestClock:
    def __init__(self, timestamps: List[int], tick_delay: float = 1.0):
        self._lock = Lock()
        self._timestamps = sorted(timestamps)
        self._current_index: int = -1
        self._tick_delay = tick_delay
        self._is_complete = False

    def reset(self) -> None:
        with self._lock:
            self._current_index = -1
            self._is_complete = False

    def tick(self) -> bool:
        with self._lock:
            if not self._timestamps or self._current_index >= len(self._timestamps):
                self._is_complete = True
                return False
            if self._current_index < len(self._timestamps):
                self._current_index = self._current_index + 1
                return self._current_index < len(self._timestamps)
            return False

    def now(self) -> int:
        with self._lock:
            if not self._timestamps:
                return 0

            # Clamp to valid range
            idx = max(0, min(self._current_index, len(self._timestamps) - 1))
            return self._timestamps[idx]

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self._current_index >= len(self._timestamps)

    @property
    def progress(self) -> float:
        with self._lock:
            if not self._timestamps:
                return 0.0
            idx = max(0, self._current_index)
            return min(idx / len(self._timestamps), 1.0)

    @property
    def total_ticks(self) -> int:
        return len(self._timestamps)
