from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from src.trading.strategies.models.strategy_schedule import (
    StrategySchedule,
    TradingWindow,
    Weekday,
)

if TYPE_CHECKING:
    from src.configuration.strategy_config import StrategyConfig
    from src.core.interfaces.trading_strategy import TradingStrategy


class StrategyWeightResolver:
    """Pure, deterministic resolver for strategy effective weights and trading windows."""

    @staticmethod
    def is_window_active(window: TradingWindow, local_dt: datetime) -> bool:
        current_weekday = Weekday(local_dt.weekday())
        current_time = local_dt.time()

        if window.start_time < window.end_time:
            if current_weekday in window.days:
                if window.start_time <= current_time < window.end_time:
                    return True
        else:
            if current_weekday in window.days and current_time >= window.start_time:
                return True
            prev_weekday = Weekday((local_dt.weekday() - 1) % 7)
            if prev_weekday in window.days and current_time < window.end_time:
                return True

        return False

    @classmethod
    def is_schedule_active(cls, schedule: StrategySchedule, dt: datetime | float) -> bool:
        if not schedule.windows:
            return False

        if isinstance(dt, (int, float)):
            utc_dt = datetime.fromtimestamp(float(dt), tz=timezone.utc)
        elif dt.tzinfo is None:
            utc_dt = dt.replace(tzinfo=timezone.utc)
        else:
            utc_dt = dt.astimezone(timezone.utc)

        tz = ZoneInfo(schedule.timezone)
        local_dt = utc_dt.astimezone(tz)

        return any(cls.is_window_active(window, local_dt) for window in schedule.windows)

    @classmethod
    def resolve_effective_weight(
            cls,
            strategy: StrategyConfig | TradingStrategy,
            timestamp: datetime | float,
    ) -> float:
        if not strategy.enabled:
            return 0.0

        if strategy.weight <= 0.0:
            return 0.0

        schedule = strategy.schedule
        if schedule is None:
            return float(strategy.weight)

        if not schedule.windows:
            return 0.0

        if cls.is_schedule_active(schedule, timestamp):
            return float(strategy.weight)

        return 0.0
