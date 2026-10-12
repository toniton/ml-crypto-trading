from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from api.interfaces.walk_forward import WalkForwardFold, WalkForwardWindowSpec, WindowMode


def _timestamp_to_datetime(timestamp: float | int) -> datetime:
    ts = (timestamp / 1000.0) if timestamp > 100000000000 else float(timestamp)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


class WalkForwardFoldGenerator:
    def __init__(self, window_spec: WalkForwardWindowSpec):
        self._window_spec = window_spec

    def generate_folds(self, timestamps: Sequence[int]) -> list[WalkForwardFold]:
        if len(timestamps) < 4:
            return []

        train_count, test_count, step_count = self._resolve_window_sizes(timestamps)
        if train_count + test_count > len(timestamps):
            return []

        folds: list[WalkForwardFold] = []
        fold_idx = 0
        current_offset = 0

        while current_offset + train_count + test_count <= len(timestamps):
            train_start_idx = (
                current_offset
                if self._window_spec.window_mode == WindowMode.ROLLING
                else 0
            )
            folds.append(
                self._create_fold(
                    fold_idx=fold_idx,
                    timestamps=timestamps,
                    train_start_idx=train_start_idx,
                    train_end_idx=current_offset + train_count - 1,
                    test_start_idx=current_offset + train_count,
                    test_end_idx=current_offset + train_count + test_count - 1,
                    warmup_count=max(0, self._window_spec.warmup_candle_count),
                )
            )
            fold_idx += 1
            current_offset += step_count

        return folds

    @staticmethod
    def _create_fold(
        fold_idx: int,
        timestamps: Sequence[int],
        train_start_idx: int,
        train_end_idx: int,
        test_start_idx: int,
        test_end_idx: int,
        warmup_count: int,
    ) -> WalkForwardFold:
        warmup_start_idx = max(0, train_start_idx - warmup_count)
        warmup_end_idx = train_start_idx - 1 if train_start_idx > warmup_start_idx else None

        warmup_start = (
            _timestamp_to_datetime(timestamps[warmup_start_idx])
            if warmup_end_idx is not None
            else None
        )
        warmup_end = (
            _timestamp_to_datetime(timestamps[warmup_end_idx])
            if warmup_end_idx is not None
            else None
        )

        test_warmup_start_idx = max(0, test_start_idx - warmup_count)
        test_warmup_start = (
            _timestamp_to_datetime(timestamps[test_warmup_start_idx])
            if test_start_idx > test_warmup_start_idx
            else None
        )

        return WalkForwardFold(
            fold_index=fold_idx,
            warmup_start=warmup_start,
            warmup_end=warmup_end,
            train_start=_timestamp_to_datetime(timestamps[train_start_idx]),
            train_end=_timestamp_to_datetime(timestamps[train_end_idx]),
            test_start=_timestamp_to_datetime(timestamps[test_start_idx]),
            test_end=_timestamp_to_datetime(timestamps[test_end_idx]),
            test_warmup_start=test_warmup_start,
            status="PENDING",
        )

    def _resolve_window_sizes(self, timestamps: Sequence[int]) -> tuple[int, int, int]:
        total = len(timestamps)

        if self._window_spec.train_candle_count and self._window_spec.test_candle_count:
            train = self._window_spec.train_candle_count
            test = self._window_spec.test_candle_count
            step = self._window_spec.step_size_candles or test
            return train, test, step

        median_delta = self._estimate_candle_interval_seconds(timestamps)
        seconds_per_day = 86400

        if self._window_spec.train_duration_days and self._window_spec.test_duration_days:
            candles_per_day = max(1, int(round(seconds_per_day / median_delta)))
            train = self._window_spec.train_duration_days * candles_per_day
            test = self._window_spec.test_duration_days * candles_per_day
            step = (
                self._window_spec.step_size_days * candles_per_day
                if self._window_spec.step_size_days
                else test
            )
            return max(2, train), max(2, test), max(1, step)

        # Default fallback heuristic: 60% train, 20% test, 20% step
        train = max(2, int(total * 0.6))
        test = max(2, int(total * 0.2))
        step = max(1, test)
        return train, test, step

    @staticmethod
    def _estimate_candle_interval_seconds(timestamps: Sequence[int]) -> float:
        if len(timestamps) < 2:
            return 86400.0
        diffs: list[float] = []
        sample_size = min(len(timestamps) - 1, 50)
        for i in range(sample_size):
            t1 = timestamps[i]
            t2 = timestamps[i + 1]
            diff = abs(t2 - t1)
            diff_sec = (diff / 1000.0) if diff > 100000000000 else float(diff)
            if diff_sec > 0:
                diffs.append(diff_sec)
        if not diffs:
            return 86400.0
        diffs.sort()
        return diffs[len(diffs) // 2]
