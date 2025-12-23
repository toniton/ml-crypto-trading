from backtest.backtest_clock import BacktestClock


class TestBacktestClock:
    def test_clock_initialization(self):
        timestamps = [1000, 2000, 3000]
        clock = BacktestClock(timestamps)

        assert clock.total_ticks == 3
        # Before first tick, index is -1. now() should return first timestamp?
        # Wait, implementation of now(): max(0, min(idx, len-1)).
        # So initially index -1 -> clamped to 0 -> timestamp 1000.
        assert clock.now() == 1000
        assert clock.is_complete is False
        assert clock.progress == 0.0

    def test_clock_ticking(self):
        timestamps = [1000, 2000]
        clock = BacktestClock(timestamps)

        # Initial state
        assert clock.now() == 1000

        # First tick
        assert clock.tick() is True
        assert clock.now() == 1000  # Index 0
        assert clock.progress == 0.0  # 0/2

        # Second tick
        assert clock.tick() is True
        assert clock.now() == 2000  # Index 1
        assert clock.progress == 0.5  # 1/2 (floored div?) No, 1/2 = 0.5

        # Third tick (should be exhausted)
        # index becomes 2 (len), returns False
        assert clock.tick() is False
        assert clock.is_complete is True
        # now() clamped to last
        assert clock.now() == 2000

    def test_empty_timestamps(self):
        clock = BacktestClock([])
        assert clock.total_ticks == 0
        assert clock.tick() is False
        assert clock.now() == 0

    def test_reset(self):
        timestamps = [1000, 2000]
        clock = BacktestClock(timestamps)

        clock.tick()
        clock.tick()
        clock.tick()  # 3rd tick to exhaust
        assert clock.is_complete is True

        clock.reset()
        assert clock.is_complete is False
        # Tick again starts from beginning
        assert clock.tick() is True
        assert clock.now() == 1000
