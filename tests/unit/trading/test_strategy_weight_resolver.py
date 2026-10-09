from datetime import datetime, time, timezone

import pytest

from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.trading.strategies.models.strategy_schedule import (
    StrategySchedule,
    TradingWindow,
    Weekday,
)
from src.trading.strategies.strategy_weight_resolver import StrategyWeightResolver


class TestStrategyWeightResolver:
    @pytest.fixture
    def stockholm_schedule(self) -> StrategySchedule:
        return StrategySchedule(
            timezone="Europe/Stockholm",
            windows=[
                TradingWindow(
                    days=[Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY],
                    start_time=time(9, 0),
                    end_time=time(16, 0),
                )
            ],
        )

    @pytest.fixture
    def active_strategy(self, stockholm_schedule: StrategySchedule) -> StrategyConfig:
        return StrategyConfig(
            name="momentum_buy",
            type=StrategyType.DYNAMIC,
            action="BUY",
            expression="close > 100",
            weight=0.8,
            enabled=True,
            schedule=stockholm_schedule,
        )

    def test_active_during_window(self, active_strategy: StrategyConfig):
        # Monday 2026-10-12 10:00:00 Stockholm time (UTC+2) -> 08:00:00 UTC
        utc_dt = datetime(2026, 10, 12, 8, 0, 0, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.8

    def test_inactive_before_window(self, active_strategy: StrategyConfig):
        # Monday 2026-10-12 08:59:59 Stockholm time -> 06:59:59 UTC
        utc_dt = datetime(2026, 10, 12, 6, 59, 59, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.0

    def test_inactive_after_window(self, active_strategy: StrategyConfig):
        # Monday 2026-10-12 16:00:00 Stockholm time -> 14:00:00 UTC (end_time is exclusive)
        utc_dt = datetime(2026, 10, 12, 14, 0, 0, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.0

    def test_inactive_on_weekend(self, active_strategy: StrategyConfig):
        # Saturday 2026-10-17 12:00:00 Stockholm time
        utc_dt = datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.0

    def test_disabled_strategy_returns_zero_in_window(self, active_strategy: StrategyConfig):
        active_strategy.enabled = False
        utc_dt = datetime(2026, 10, 12, 8, 0, 0, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.0

    def test_zero_base_weight_returns_zero_in_window(self, active_strategy: StrategyConfig):
        active_strategy.weight = 0.0
        utc_dt = datetime(2026, 10, 12, 8, 0, 0, tzinfo=timezone.utc)
        weight = StrategyWeightResolver.resolve_effective_weight(active_strategy, utc_dt)
        assert weight == 0.0

    def test_empty_schedule_returns_zero_at_all_times(self):
        strategy = StrategyConfig(
            name="static_hammer",
            type=StrategyType.STATIC,
            class_name="HammerAccumulationStrategy",
            weight=1.0,
            enabled=True,
            schedule=StrategySchedule(timezone="UTC", windows=[]),
        )
        utc_dt = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, utc_dt) == 0.0

    def test_overnight_window_spanning_midnight(self):
        # Sunday night to Monday morning: 22:00 to 04:00
        schedule = StrategySchedule(
            timezone="UTC",
            windows=[
                TradingWindow(
                    days=[Weekday.SUNDAY],
                    start_time=time(22, 0),
                    end_time=time(4, 0),
                )
            ],
        )
        strategy = StrategyConfig(
            name="overnight",
            type=StrategyType.DYNAMIC,
            action="BUY",
            expression="close > 10",
            weight=1.0,
            schedule=schedule,
        )

        # Sunday 23:00 UTC -> active
        sunday_night = datetime(2026, 10, 11, 23, 0, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, sunday_night) == 1.0

        # Monday 02:00 UTC -> active (continuation of Sunday night window)
        monday_early = datetime(2026, 10, 12, 2, 0, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, monday_early) == 1.0

        # Monday 04:30 UTC -> inactive
        monday_after = datetime(2026, 10, 12, 4, 30, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, monday_after) == 0.0

    def test_multiple_non_overlapping_windows(self):
        # Morning window (09:00-12:00) and Afternoon window (14:00-17:00)
        schedule = StrategySchedule(
            timezone="UTC",
            windows=[
                TradingWindow(days=[Weekday.WEDNESDAY], start_time=time(9, 0), end_time=time(12, 0)),
                TradingWindow(days=[Weekday.WEDNESDAY], start_time=time(14, 0), end_time=time(17, 0)),
            ],
        )
        strategy = StrategyConfig(
            name="two_session",
            type=StrategyType.DYNAMIC,
            action="BUY",
            expression="close > 10",
            weight=0.5,
            schedule=schedule,
        )

        # 10:00 UTC -> active (morning)
        morning_dt = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, morning_dt) == 0.5

        # 13:00 UTC -> inactive (lunch gap)
        lunch_dt = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, lunch_dt) == 0.0

        # 15:30 UTC -> active (afternoon)
        afternoon_dt = datetime(2026, 10, 14, 15, 30, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, afternoon_dt) == 0.5

    def test_dst_transition_handling(self):
        # Stockholm changes from CEST (UTC+2) to CET (UTC+1) on the last Sunday of October
        schedule = StrategySchedule(
            timezone="Europe/Stockholm",
            windows=[
                TradingWindow(days=[Weekday.MONDAY], start_time=time(9, 0), end_time=time(10, 0)),
            ],
        )
        strategy = StrategyConfig(
            name="dst_test",
            type=StrategyType.DYNAMIC,
            action="BUY",
            expression="close > 10",
            weight=1.0,
            schedule=schedule,
        )

        # Summer (CEST = UTC+2): Monday 2026-08-10 at 07:30 UTC is 09:30 Stockholm -> active
        summer_time = datetime(2026, 8, 10, 7, 30, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, summer_time) == 1.0

        # Winter (CET = UTC+1): Monday 2026-11-09 at 07:30 UTC is 08:30 Stockholm -> inactive
        winter_too_early = datetime(2026, 11, 9, 7, 30, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, winter_too_early) == 0.0

        # Winter (CET = UTC+1): Monday 2026-11-09 at 08:30 UTC is 09:30 Stockholm -> active
        winter_active = datetime(2026, 11, 9, 8, 30, 0, tzinfo=timezone.utc)
        assert StrategyWeightResolver.resolve_effective_weight(strategy, winter_active) == 1.0

    def test_float_epoch_timestamp_input(self, active_strategy: StrategyConfig):
        # Unix timestamp for Monday 2026-10-12 10:00:00 Stockholm time (UTC 08:00:00)
        dt = datetime(2026, 10, 12, 8, 0, 0, tzinfo=timezone.utc)
        epoch = dt.timestamp()
        assert StrategyWeightResolver.resolve_effective_weight(active_strategy, epoch) == 0.8
