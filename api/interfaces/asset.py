#!/usr/bin/env python3
from typing import Optional

from pydantic import computed_field
from pydantic.dataclasses import dataclass

from api.interfaces.asset_schedule import AssetSchedule
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum
from api.interfaces.timeframe import Timeframe
from src.configuration.guard_config import GuardConfig


@dataclass
class Asset:
    base_ticker_symbol: str
    quote_ticker_symbol: str
    decimal_places: int
    name: str
    exchange: ExchangeProvidersEnum
    min_quantity: float
    schedule: AssetSchedule
    candles_timeframe: Timeframe
    guard_config: Optional[GuardConfig] = None
    keywords: Optional[list[str]] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None

    @computed_field
    @property
    def ticker_symbol(self) -> str:
        return f"{self.base_ticker_symbol}_{self.quote_ticker_symbol}"

    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")
