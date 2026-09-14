from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MergeStatus(str, Enum):
    CLEAN = "CLEAN"
    CONFLICT = "CONFLICT"
    INCOMPATIBLE_SCHEMA = "INCOMPATIBLE_SCHEMA"
    FAST_FORWARD = "FAST_FORWARD"


class FieldConflict(BaseModel):
    path: str
    base_value: Any = None
    ours_value: Any = None
    theirs_value: Any = None
    description: str = ""


class MergePreview(BaseModel):
    status: MergeStatus
    merge_base_hash: str
    target_head_hash: str
    source_commit_hash: str
    can_fast_forward: bool = False
    conflicts: List[FieldConflict] = Field(default_factory=list)
    merged_config: Optional[Dict[str, Any]] = None
    validation_errors: List[str] = Field(default_factory=list)


class MergeResult(BaseModel):
    merge_commit_hash: str
    target_ref: str
    source_commit_hash: str
    status: str = "MERGED"
    message: str
    parents: List[str] = Field(default_factory=list)
