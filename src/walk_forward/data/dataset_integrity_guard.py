from __future__ import annotations

from typing import Sequence

from api.interfaces.candle import Candle
from src.backtest.backtest_data_loader import HistoricalDataPoint


class DatasetIntegrityError(ValueError):
    pass


class DatasetIntegrityGuard:
    @staticmethod
    def validate_historical_points(
            points: Sequence[HistoricalDataPoint],
            min_required_points: int = 10,
            require_volume: bool = False,
    ) -> None:
        if not points:
            raise DatasetIntegrityError("Historical dataset is empty.")

        if len(points) < min_required_points:
            raise DatasetIntegrityError(
                f"Insufficient historical data: {len(points)} observations provided, "
                f"at least {min_required_points} required."
            )

        prev_timestamp = -1
        zero_volume_count = 0

        for idx, pt in enumerate(points):
            if pt.timestamp <= prev_timestamp:
                raise DatasetIntegrityError(
                    f"Dataset timestamp order violation at index {idx}: "
                    f"timestamp {pt.timestamp} <= previous {prev_timestamp}"
                )
            prev_timestamp = pt.timestamp

            if pt.volume <= 0:
                zero_volume_count += 1

        if require_volume and zero_volume_count == len(points):
            raise DatasetIntegrityError("Historical dataset lacks volume data across all observations.")

    @staticmethod
    def validate_candles(
            candles: Sequence[Candle],
            min_required_candles: int = 10,
    ) -> None:
        if not candles:
            raise DatasetIntegrityError("Candle dataset is empty.")

        if len(candles) < min_required_candles:
            raise DatasetIntegrityError(
                f"Insufficient candles: {len(candles)} candles provided, "
                f"at least {min_required_candles} required."
            )

        prev_time = -1.0
        for idx, candle in enumerate(candles):
            if candle.start_time <= prev_time:
                raise DatasetIntegrityError(
                    f"Candle sequence timestamp order violation at index {idx}: "
                    f"start_time {candle.start_time} <= previous {prev_time}"
                )
            prev_time = candle.start_time
