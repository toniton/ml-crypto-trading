from dataclasses import dataclass
from threading import Lock


@dataclass
class AssetClockData:
    current_index: int = -1
    timestamps: list[int] = ()
    is_complete: bool = False


class BacktestClock:
    def __init__(self, timestamps: dict[str, list[int]], tick_delay: float = 1.0):
        self._lock = Lock()
        self._tick_delay = tick_delay
        self._asset_clock_indexes: dict[str, AssetClockData] = {}

        for key, ts_list in timestamps.items():
            self._asset_clock_indexes[key] = AssetClockData(timestamps=sorted(ts_list), current_index=-1,
                                                            is_complete=False)

    def reset(self, key: str) -> None:
        with self._lock:
            if key not in self._asset_clock_indexes:
                raise ValueError(f"Asset with key '{key}' not found")
            self._asset_clock_indexes[key].current_index = -1
            self._asset_clock_indexes[key].is_complete = False

    def tick(self, key: str) -> bool:
        with self._lock:
            clock_data = self._asset_clock_indexes[key]
            timestamp_length = len(clock_data.timestamps)
            if not clock_data or clock_data.current_index >= timestamp_length:
                clock_data.is_complete = True
                return False
            if clock_data.current_index < timestamp_length:
                clock_data.current_index = clock_data.current_index + 1
                return clock_data.current_index < timestamp_length
            return False

    def now(self, key: str) -> int:
        with self._lock:
            clock_data = self._asset_clock_indexes[key]
            if not clock_data:
                return 0

            timestamp_length = len(clock_data.timestamps)
            if timestamp_length == 0:
                return 0

            idx = max(0, min(clock_data.current_index, timestamp_length - 1))
            return clock_data.timestamps[idx]

    def is_complete(self, key: str) -> bool:
        with self._lock:
            clock_data = self._asset_clock_indexes[key]
            return clock_data.current_index >= len(clock_data.timestamps)

    def progress(self, key: str) -> float:
        with self._lock:
            clock_data = self._asset_clock_indexes[key]
            if not clock_data:
                return 0.0
            idx = max(0, clock_data.current_index)
            return min(idx / len(clock_data.timestamps), 1.0)

    def total_ticks(self, key: str) -> int:
        clock_data = self._asset_clock_indexes[key]
        return len(clock_data.timestamps)
