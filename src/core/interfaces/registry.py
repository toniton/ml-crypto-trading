from __future__ import annotations

from abc import ABC
from typing import Generic, TypeVar

K = TypeVar('K')
V = TypeVar('V')


class Registry(ABC, Generic[K, V]):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._entries: dict[K, list[V]] = {}

    def _register(self, key: K, entry: V) -> None:
        self._entries.setdefault(key, []).append(entry)

    def _get(self, key: K) -> list[V]:
        entries = self._entries.get(key)
        if entries is None:
            raise ValueError(f"Key '{key}' not registered.")
        return entries.copy()

    def _get_first(self, key: K) -> V:
        entries = self._entries.get(key)
        if entries is None or not entries:
            raise ValueError(f"Key '{key}' not registered or empty.")
        return entries[0]

    def _keys(self) -> list[K]:
        return list(self._entries.keys())

    def __contains__(self, key: K) -> bool:
        return key in self._entries
