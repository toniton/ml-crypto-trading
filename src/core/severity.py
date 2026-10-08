from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"

    @classmethod
    def from_value(cls, value: str | Severity | None, default: Severity = INFO) -> Severity:
        if isinstance(value, cls):
            return value
        if value is None or not str(value).strip():
            return default
        val_str = str(value).strip().upper()
        try:
            return cls(val_str)
        except ValueError:
            return default

    @property
    def is_critical_or_higher(self) -> bool:
        return self in (Severity.CRITICAL, Severity.FATAL)

    @property
    def is_warning(self) -> bool:
        return self == Severity.WARNING

    @property
    def is_error_or_higher(self) -> bool:
        return self in (Severity.ERROR, Severity.CRITICAL, Severity.FATAL)
