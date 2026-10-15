from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field




class RunRequest(BaseModel):
    confirm: bool = Field(default=False, description="Explicit confirmation of a destructive run.")


class UpdatePolicyRequest(BaseModel):
    retention_period: Optional[str] = Field(default=None, description="Duration such as 90d or KEEP.")
    retention_mode: Optional[str] = Field(default=None, description="DELETE, ARCHIVE, AGGREGATE_THEN_DELETE or KEEP.")
    enabled: Optional[bool] = Field(default=None, description="Whether automated enforcement is active.")
    confirm: bool = Field(default=False, description="Confirmation when shortening retention.")
    actor: Optional[str] = Field(default=None, description="Operator performing the change.")
