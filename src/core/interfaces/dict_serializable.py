from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DictSerializable(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...
