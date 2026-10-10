from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ConfigChange(BaseModel):
    path: str = Field(description="Dot-separated config path, e.g. 'assets.BTC_USD.schedule'.")
    old_value: Any = Field(default=None, description="The current value of the field.")
    new_value: Any = Field(default=None, description="The proposed replacement value.")
    reason: str = Field(default="", description="Why this change is required to reach the user's goal.")


class ConfigurationProposal(BaseModel):
    summary: str = Field(description="Short human-readable summary of the proposal.")
    changes: list[ConfigChange] = Field(description="The patch entries to apply.")
    risks: list[str] = Field(default_factory=list, description="Potential downsides of the changes.")
    expected_effect: str = Field(
        default="",
        description="What behaviour change the user can expect once the proposal is applied.",
    )
