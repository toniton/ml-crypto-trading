#!/usr/bin/env python3
from pydantic import BaseModel
from pydantic.dataclasses import dataclass


class MarketData(BaseModel):
    volume: str
    high_price: str
    low_price: str
    close_price: str
    timestamp: int
