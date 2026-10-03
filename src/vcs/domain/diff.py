from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ConfigChange(BaseModel):
    path: str = Field(description="Dot-separated config path, e.g. 'assets.BTC_USD.schedule'.")
    old_value: Any = Field(default=None, description="The current value of the field.")
    new_value: Any = Field(default=None, description="The proposed replacement value.")
    reason: str = Field(default="", description="Why this change is required to reach the user's goal.")
