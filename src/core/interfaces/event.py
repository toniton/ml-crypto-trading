from abc import ABC, abstractmethod
from typing import ClassVar, Generic, Optional, TypeVar

T = TypeVar("T")


class Event(ABC, Generic[T]):
    EVENT_TYPE: ClassVar[Optional[str]] = None

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
