from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class Blob(BaseModel):
    model_config = ConfigDict(frozen=True)

    hash: str
    content: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
