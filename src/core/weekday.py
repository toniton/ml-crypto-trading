from __future__ import annotations

from enum import IntEnum


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @property
    def is_weekday(self) -> bool:
        return self <= Weekday.FRIDAY

    @property
    def is_weekend(self) -> bool:
        return self >= Weekday.SATURDAY
