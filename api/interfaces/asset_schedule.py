from enum import Enum


class AssetSchedule(Enum):
    EVERY_SECOND = 0
    EVERY_MINUTE = 1
    EVERY_HOUR = 2
    EVERY_DAY = 3
    EVERY_WEEK = 4
    EVERY_MONTH = 5
