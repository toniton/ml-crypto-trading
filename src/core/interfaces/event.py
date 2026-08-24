from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Event(ABC, Generic[T]):
    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def type(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def payload(self) -> T:
        raise NotImplementedError()

    @property
    @abstractmethod
    def metadata(self) -> dict:
        raise NotImplementedError()

    @property
    @abstractmethod
    def timestamp(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def to_dict(self) -> dict:
        raise NotImplementedError()
