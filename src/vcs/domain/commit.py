from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class Commit(BaseModel):
    model_config = ConfigDict(frozen=True)

    hash: str
    blob_hash: str
    parent_hash: Optional[str]
    author: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
