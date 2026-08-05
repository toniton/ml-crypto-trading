from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Reference(BaseModel):
    name: str
    commit_hash: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
