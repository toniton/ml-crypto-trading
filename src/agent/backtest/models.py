from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from api.interfaces.backtest_request import BacktestDataSourceType
from src.agent.configuration.models import MarkdownBlock


class BacktestTimeRange(BaseModel):
    """How the user scoped the backtest in time.

    Either a relative window (e.g. "last 5 minutes") or an absolute one.
    The LLM never computes timestamps itself; it only states the intent.
    """

    mode: Literal["relative", "absolute"] = "relative"
    duration_seconds: Optional[int] = Field(
        default=None,
        description="Relative window length in seconds (e.g. 300 for 5 minutes).",
    )
    start_time: Optional[datetime] = Field(
        default=None,
        description="Explicit start time for absolute ranges.",
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="Explicit end time for absolute ranges.",
    )


class BacktestAgentRequest(BaseModel):
    """What the user means — not yet the execution contract."""

    ticker_symbol: Optional[str] = Field(
        default=None,
        description="The asset to backtest (e.g. 'BTC_USD'), or null if unspecified.",
    )
    time_range: BacktestTimeRange = BacktestTimeRange()


    data_source: BacktestDataSourceType = Field(
        default=BacktestDataSourceType.MARKET_DATA,
        description="Where the historical data should come from.",
    )
    configuration_changes: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy/parameter overrides the user wants to test.",
    )
    fee_rate: Optional[float] = Field(
        default=None,
        description=(
            "Trading fee rate as a decimal fraction (e.g. 0.001 for 0.1%). "
            "Null when the user has not specified it."
        ),
    )
    slippage_ticks: Optional[int] = Field(
        default=None,
        description="Slippage in ticks. Null when the user has not specified it.",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Order execution latency in milliseconds. Null when not specified.",
    )
    requires_clarification: bool = Field(
        default=False,
        description="True when the request is too vague to run without asking.",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="The question to ask when requires_clarification is true.",
    )


class BacktestValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def ok(cls, warnings: Optional[list[str]] = None) -> "BacktestValidation":
        return cls(valid=True, warnings=warnings or [])

    @classmethod
    def failed(cls, errors: list[str], warnings: Optional[list[str]] = None) -> "BacktestValidation":
        return cls(valid=False, errors=errors, warnings=warnings or [])


class BacktestQuality(BaseModel):
    """A guardrail for statistically meaningless results."""

    sufficient_evidence: bool = True
    notes: list[str] = Field(default_factory=list)


class BacktestPresentation(BaseModel):
    blocks: list[MarkdownBlock] = Field(default_factory=list)
