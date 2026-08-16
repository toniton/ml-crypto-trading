from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefChangedEvent:
    ref: str
    commit_hash: str
