from __future__ import annotations

from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class MultiRegistry(Generic[K, V]):
    """A one-to-many registry: each key maps to an ordered list of values."""

    def __init__(self) -> None:
        self._entries: dict[K, list[V]] = {}

    def register(self, key: K, entry: V) -> None:
        self._entries.setdefault(key, []).append(entry)

    def get(self, key: K) -> list[V]:
        try:
            return self._entries[key].copy()
        except KeyError:
            raise ValueError(f"Key '{key}' not registered.") from None

    def get_first(self, key: K) -> V:
        entries = self.get(key)

        if not entries:
            raise ValueError(f"Key '{key}' registered but empty.")

        return entries[0]

    def unregister(self, key: K, entry: V) -> None:
        entries = self._entries.get(key)

        if entries is None:
            raise ValueError(f"Key '{key}' not registered.")

        try:
            entries.remove(entry)
        except ValueError:
            raise ValueError(f"Entry {entry!r} not registered under key '{key}'.") from None

        if not entries:
            del self._entries[key]

    def keys(self) -> list[K]:
        return list(self._entries)

    def __contains__(self, key: K) -> bool:
        return key in self._entries
