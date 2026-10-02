from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LlmCredential(BaseModel):
    id: Optional[int] = None
    model_id: str
    provider: str
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    is_active: bool = False
    created_timestamp: Optional[datetime] = None
    last_updated_timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
