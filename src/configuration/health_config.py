from __future__ import annotations

from pydantic import BaseModel, Field


class HealthRecoveryConfig(BaseModel):
    automatic: bool = Field(
        default=True,
        description="Whether healthy checks can automatically resolve non-fatal conditions.",
        json_schema_extra={"mutable": True},
    )
    stable_period_seconds: float = Field(
        default=10.0,
        ge=0.0,
        description="Minimum duration in seconds a subsystem must remain stable to resolve.",
        json_schema_extra={"mutable": True},
    )
    required_successful_checks: int = Field(
        default=3,
        ge=1,
        description="Number of consecutive healthy checks required before resolving an active condition.",
        json_schema_extra={"mutable": True},
    )


class HealthThresholdsConfig(BaseModel):
    market_data_stale_seconds: float = Field(
        default=10.0,
        ge=1.0,
        description="Threshold in seconds beyond which market data is considered stale.",
        json_schema_extra={"mutable": True},
    )
    exchange_unavailable_seconds: float = Field(
        default=15.0,
        ge=1.0,
        description="Threshold in seconds for exchange connection loss before triggering pause.",
        json_schema_extra={"mutable": True},
    )
    balance_mismatch_tolerance: float = Field(
        default=0.01,
        ge=0.0,
        description="Absolute tolerance difference for balance reconciliation.",
        json_schema_extra={"mutable": True},
    )
    order_reconciliation_interval_seconds: float = Field(
        default=30.0,
        ge=1.0,
        description="Interval in seconds for periodic order reconciliation checks.",
        json_schema_extra={"mutable": True},
    )


class HealthConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether trading health monitoring and state machine enforcement is enabled.",
        json_schema_extra={"mutable": True},
    )
    recovery: HealthRecoveryConfig = Field(
        default_factory=HealthRecoveryConfig,
        description="Recovery policies and hysteresis settings.",
        json_schema_extra={"mutable": True},
    )
    thresholds: HealthThresholdsConfig = Field(
        default_factory=HealthThresholdsConfig,
        description="Thresholds for triggering health conditions.",
        json_schema_extra={"mutable": True},
    )
