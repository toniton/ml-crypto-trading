from datetime import time
import pytest
from pydantic import ValidationError

from api.interfaces.trade_action import TradeAction
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.trading.strategies.models.strategy_schedule import (
    StrategySchedule,
    TradingWindow,
    Weekday,
)


class TestStrategyScheduleModels:
    def test_trading_window_valid(self):
        window = TradingWindow(
            days=[Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY],
            start_time=time(9, 0),
            end_time=time(16, 0),
        )
        assert window.days == [Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY]
        assert window.start_time == time(9, 0)
        assert window.end_time == time(16, 0)

    def test_trading_window_deduplicates_and_sorts_days(self):
        window = TradingWindow(
            days=[Weekday.FRIDAY, Weekday.MONDAY, Weekday.MONDAY],
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        assert window.days == [Weekday.MONDAY, Weekday.FRIDAY]

    def test_trading_window_rejects_empty_days(self):
        with pytest.raises(ValidationError, match="at least one active day"):
            TradingWindow(
                days=[],
                start_time=time(9, 0),
                end_time=time(16, 0),
            )

    def test_trading_window_rejects_identical_start_and_end_time(self):
        with pytest.raises(ValidationError, match="cannot be identical"):
            TradingWindow(
                days=[Weekday.MONDAY],
                start_time=time(10, 0),
                end_time=time(10, 0),
            )

    def test_strategy_schedule_valid_timezone(self):
        schedule = StrategySchedule(
            timezone="America/New_York",
            windows=[
                TradingWindow(
                    days=[Weekday.MONDAY, Weekday.TUESDAY],
                    start_time=time(9, 30),
                    end_time=time(16, 0),
                )
            ],
        )
        assert schedule.timezone == "America/New_York"
        assert len(schedule.windows) == 1

    def test_strategy_schedule_default_timezone_is_utc(self):
        schedule = StrategySchedule()
        assert schedule.timezone == "UTC"

    def test_strategy_schedule_rejects_invalid_timezone(self):
        with pytest.raises(ValidationError, match="Invalid IANA timezone"):
            StrategySchedule(
                timezone="Invalid/Timezone_Name",
                windows=[],
            )

    def test_strategy_config_includes_weight_and_schedule(self):
        config = StrategyConfig(
            name="momentum",
            type=StrategyType.DYNAMIC,
            action="BUY",
            expression="close > 100",
            weight=0.75,
            schedule=StrategySchedule(
                timezone="Europe/Stockholm",
                windows=[
                    TradingWindow(
                        days=[Weekday.MONDAY],
                        start_time=time(9, 0),
                        end_time=time(17, 30),
                    )
                ],
            ),
        )
        assert config.weight == 0.75
        assert isinstance(config.schedule, StrategySchedule)
        assert config.schedule.timezone == "Europe/Stockholm"  # pylint: disable=no-member
        assert len(config.schedule.windows) == 1  # pylint: disable=no-member

    def test_strategy_config_rejects_negative_weight(self):
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="momentum",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=-0.5,
            )
