from backtest.backtest_clock import BacktestClock


class TestBacktestClock:
    def test_clock_initialization(self):
        timestamps = {"btc": [1000, 2000, 3000]}
        clock = BacktestClock(timestamps)

        assert clock.total_ticks("btc") == 3
        # Before first tick, index is -1. now() should return first timestamp
        assert clock.now("btc") == 1000
        assert clock.is_complete("btc") is False
        assert clock.progress("btc") == 0.0

    def test_clock_ticking(self):
        timestamps = {"btc": [1000, 2000]}
        clock = BacktestClock(timestamps)

        # Initial state
        assert clock.now("btc") == 1000

        # First tick
        assert clock.tick("btc") is True
        assert clock.now("btc") == 1000  # Index 0
        assert clock.progress("btc") == 0.0

        # Second tick
        assert clock.tick("btc") is True
        assert clock.now("btc") == 2000  # Index 1
        assert clock.progress("btc") == 0.5

        # Third tick (should be exhausted)
        assert clock.tick("btc") is False
        assert clock.is_complete("btc") is True
        assert clock.now("btc") == 2000

    def test_empty_timestamps(self):
        clock = BacktestClock({"btc": []})
        assert clock.total_ticks("btc") == 0
        assert clock.tick("btc") is False
        assert clock.now("btc") == 0

    def test_reset(self):
        timestamps = {"btc": [1000, 2000]}
        clock = BacktestClock(timestamps)

        clock.tick("btc")
        clock.tick("btc")
        clock.tick("btc")  # 3rd tick to exhaust
        assert clock.is_complete("btc") is True

        clock.reset("btc")
        assert clock.is_complete("btc") is False
        # Tick again starts from beginning
        assert clock.tick("btc") is True
        assert clock.now("btc") == 1000
