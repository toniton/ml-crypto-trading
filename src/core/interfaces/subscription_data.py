from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

from pydantic.dataclasses import dataclass

from api.interfaces.account_balance import AccountBalance
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order


class SubscriptionVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"


T = TypeVar('T')


@dataclass
class SubscriptionData(Generic[T]):
    subscribe_payload: dict
    unsubscribe_payload: Optional[dict] = None
    visibility: SubscriptionVisibility = SubscriptionVisibility.PUBLIC
    parser: Optional[Callable[[dict], T]] = None

    def parse(self, data: dict) -> T:
        if self.parser is None:
            raise ValueError("No parser provided for this subscription")
        return self.parser(data)


@dataclass
class BalanceSubscriptionData(SubscriptionData[list[AccountBalance]]):
    def __post_init__(self):
        self.visibility = SubscriptionVisibility.PRIVATE


@dataclass
class OrderUpdateSubscriptionData(SubscriptionData[list[Order]]):
    def __post_init__(self):
        self.visibility = SubscriptionVisibility.PRIVATE


@dataclass
class MarketDataSubscriptionData(SubscriptionData[MarketData]):
    def __post_init__(self):
        self.visibility = SubscriptionVisibility.PUBLIC
