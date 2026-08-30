from src.backtest.backtest_clock import BacktestClock


class TestBacktestClock:
    def test_clock_initialization(self):
        timestamps = {"btc": [1000, 2000, 3000]}
        clock = BacktestClock(timestamps)

        assert clock.total_ticks("btc") == 3
        assert clock.now("btc") == 1000
        assert clock.is_complete("btc") is False
        assert clock.progress("btc") == 0.0

    def test_clock_ticking(self):
        timestamps = {"btc": [1000, 2000]}
        clock = BacktestClock(timestamps)

        assert clock.now("btc") == 1000

        assert clock.tick("btc") is True
        assert clock.now("btc") == 1000
        assert clock.progress("btc") == 0.0

        assert clock.tick("btc") is True
        assert clock.now("btc") == 2000
        assert clock.progress("btc") == 0.5

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
        clock.tick("btc")
        assert clock.is_complete("btc") is True

        clock.reset("btc")
        assert clock.is_complete("btc") is False
        assert clock.tick("btc") is True
        assert clock.now("btc") == 1000


class TestNextTimestampAtOrAfter:
    def test_exact_match(self):
        clock = BacktestClock({"btc": [1000, 2000, 3000]})
        assert clock.next_timestamp_at_or_after("btc", 2000) == 2000

    def test_between_timestamps(self):
        clock = BacktestClock({"btc": [1000, 2000, 3000]})
        assert clock.next_timestamp_at_or_after("btc", 1500) == 2000

    def test_before_first(self):
        clock = BacktestClock({"btc": [1000, 2000, 3000]})
        assert clock.next_timestamp_at_or_after("btc", 500) == 1000

    def test_past_end_returns_none(self):
        clock = BacktestClock({"btc": [1000, 2000, 3000]})
        assert clock.next_timestamp_at_or_after("btc", 4000) is None

    def test_empty_timestamps(self):
        clock = BacktestClock({"btc": []})
        assert clock.next_timestamp_at_or_after("btc", 1000) is None

    def test_unknown_symbol(self):
        clock = BacktestClock({"btc": [1000, 2000]})
        assert clock.next_timestamp_at_or_after("eth", 1000) is None

    def test_irregular_timestamps(self):
        clock = BacktestClock({"btc": [100, 150, 500, 1000]})
        assert clock.next_timestamp_at_or_after("btc", 160) == 500
        assert clock.next_timestamp_at_or_after("btc", 500) == 500
        assert clock.next_timestamp_at_or_after("btc", 501) == 1000

    def test_float_target_coerced(self):
        clock = BacktestClock({"btc": [1000, 2000, 3000]})
        assert clock.next_timestamp_at_or_after("btc", 1999.5) == 2000
