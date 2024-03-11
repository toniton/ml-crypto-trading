#!/usr/bin/env python3
from pydantic.dataclasses import dataclass


@dataclass
class MarketData:
    volume: str
    high_price: str
    low_price: str
    close_price: str
    timestamp: int
