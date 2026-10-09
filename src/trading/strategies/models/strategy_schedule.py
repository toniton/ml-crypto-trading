from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.weekday import Weekday


class TradingWindow(BaseModel):
    days: list[Weekday] = Field(
        default_factory=list,
        description="Days of the week when this window is active.",
        json_schema_extra={"mutable": True},
    )
    start_time: time = Field(
        description="Daily window start time (inclusive), e.g. 09:00:00",
        json_schema_extra={"mutable": True},
    )
    end_time: time = Field(
        description="Daily window end time (exclusive), e.g. 16:00:00",
        json_schema_extra={"mutable": True},
    )

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: list[Weekday]) -> list[Weekday]:
        if not v:
            raise ValueError("Trading window must specify at least one active day")
        return sorted(list(set(v)))

    @model_validator(mode="after")
    def validate_time_range(self) -> TradingWindow:
        if self.start_time == self.end_time:
            raise ValueError("Window start_time and end_time cannot be identical")
        return self


class StrategySchedule(BaseModel):
    timezone: str = Field(
        default="Europe/Stockholm",
        description="IANA timezone identifier (e.g. Europe/Stockholm, UTC, America/New_York)",
        json_schema_extra={"mutable": True},
    )
    windows: list[TradingWindow] = Field(
        default_factory=list,
        description="Recurring weekly active intervals. Empty list means inactive at all times.",
        json_schema_extra={"mutable": True},
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid IANA timezone: '{v}'") from exc
        return v
