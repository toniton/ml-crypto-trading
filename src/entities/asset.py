#!/usr/bin/env python3
from typing import Optional

from pydantic import BaseModel, computed_field

from api.interfaces.exchange_provider import ExchangeProvidersEnum
from api.interfaces.timeframe import Timeframe
from src.configuration.guard_config import GuardConfig


class Asset(BaseModel):
    keywords: list[str]
    ticker_symbol: str
    decimal_places: int
    name: str
    market_cap: float
    exchange: ExchangeProvidersEnum
    min_quantity: float
    sector: str
    industry: str
    candles_timeframe: Timeframe
    guard_config: Optional[GuardConfig] = None

    @computed_field
    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")
