from __future__ import annotations

from decimal import Decimal

import pytest

from api.interfaces.walk_forward import WalkForwardWindowSpec, WindowMode
from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.walk_forward.data.dataset_integrity_guard import (
    DatasetIntegrityError,
    DatasetIntegrityGuard,
)
from src.walk_forward.generator.fold_generator import WalkForwardFoldGenerator


def _make_point(ts: int, volume: float = 100.0) -> HistoricalDataPoint:
    return HistoricalDataPoint(
        timestamp=ts,
        open_price=Decimal("100.0"),
        high_price=Decimal("105.0"),
        low_price=Decimal("95.0"),
        close_price=Decimal("102.0"),
        volume=Decimal(str(volume)),
        market_cap=Decimal("1000000.0"),
    )


class TestDatasetIntegrityGuard:
    def test_fails_on_empty_dataset(self):
        with pytest.raises(DatasetIntegrityError):
            DatasetIntegrityGuard.validate_historical_points([])

    def test_fails_on_unordered_timestamps(self):
        pts = [_make_point(100), _make_point(90), _make_point(110)]
        with pytest.raises(DatasetIntegrityError):
            DatasetIntegrityGuard.validate_historical_points(pts, min_required_points=3)

    def test_fails_on_missing_volume_when_required(self):
        pts = [_make_point(100 + i * 10, volume=0.0) for i in range(15)]
        with pytest.raises(DatasetIntegrityError):
            DatasetIntegrityGuard.validate_historical_points(
                pts, min_required_points=10, require_volume=True
            )

    def test_passes_on_valid_dataset(self):
        pts = [_make_point(100 + i * 10, volume=50.0) for i in range(15)]
        DatasetIntegrityGuard.validate_historical_points(pts, min_required_points=10)


class TestWalkForwardFoldGenerator:
    def test_generates_chronological_rolling_folds(self):
        timestamps = [1000 + i * 3600 for i in range(100)]
        spec = WalkForwardWindowSpec(
            train_candle_count=30,
            test_candle_count=10,
            step_size_candles=10,
            warmup_candle_count=5,
            window_mode=WindowMode.ROLLING,
        )
        generator = WalkForwardFoldGenerator(spec)
        folds = generator.generate_folds(timestamps)

        assert len(folds) == 7
        assert folds[0].fold_index == 0
        assert folds[0].train_start < folds[0].train_end
        assert folds[0].train_end < folds[0].test_start
        assert folds[0].test_start < folds[0].test_end

    def test_zero_leakage_between_train_and_test(self):
        timestamps = [1000 + i * 3600 for i in range(50)]
        spec = WalkForwardWindowSpec(
            train_candle_count=20,
            test_candle_count=10,
            step_size_candles=10,
            window_mode=WindowMode.ROLLING,
        )
        generator = WalkForwardFoldGenerator(spec)
        folds = generator.generate_folds(timestamps)

        for fold in folds:
            assert fold.train_end < fold.test_start

    def test_generates_expanding_folds(self):
        timestamps = [1000 + i * 3600 for i in range(80)]
        spec = WalkForwardWindowSpec(
            train_candle_count=20,
            test_candle_count=10,
            step_size_candles=10,
            window_mode=WindowMode.EXPANDING,
        )
        generator = WalkForwardFoldGenerator(spec)
        folds = generator.generate_folds(timestamps)

        assert len(folds) == 6
        first_train_start = folds[0].train_start
        for fold in folds:
            assert fold.train_start == first_train_start
