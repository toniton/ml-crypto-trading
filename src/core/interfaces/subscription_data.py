from __future__ import annotations

from enum import Enum
from typing import Callable, Generic, Optional, TypeVar
from dataclasses import dataclass


class SubscriptionVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"


T = TypeVar('T')


@dataclass
class SubscriptionData(Generic[T]):
    payload: dict
    visibility: SubscriptionVisibility = SubscriptionVisibility.PUBLIC
    parser: Optional[Callable[[dict], T]] = None
    filter: Optional[Callable[[dict], bool]] = None

    def parse(self, data: dict) -> T:
        if self.parser is None:
            raise ValueError("No parser provided for this subscription")
        return self.parser(data)

    def matches(self, data: dict) -> bool:
        if self.filter is None:
            return True
        return self.filter(data)
