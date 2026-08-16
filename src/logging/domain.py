from enum import Enum


class LogDomain(str, Enum):
    APPLICATION = 'application'
    TRADING = 'trading'
    AUDIT = 'audit'
