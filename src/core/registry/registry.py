from __future__ import annotations

from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class Registry(Generic[K, V]):
    """A one-to-one registry: each key maps to a single value."""

    def __init__(self) -> None:
        self._entries: dict[K, V] = {}

    def register(self, key: K, entry: V) -> None:
        if key in self._entries:
            raise ValueError(f"Key '{key}' already registered.")

        self._entries[key] = entry

    def replace(self, key: K, entry: V) -> None:
        self._entries[key] = entry

    def get(self, key: K) -> V:
        try:
            return self._entries[key]
        except KeyError:
            raise ValueError(f"Key '{key}' not registered.") from None

    def find(self, key: K) -> V | None:
        return self._entries.get(key)

    def unregister(self, key: K) -> V:
        try:
            return self._entries.pop(key)
        except KeyError:
            raise ValueError(f"Key '{key}' not registered.") from None

    def keys(self) -> list[K]:
        return list(self._entries)

    def __contains__(self, key: K) -> bool:
        return key in self._entries
