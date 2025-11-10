#!/usr/bin/env python3
from typing import Optional

from pydantic import computed_field
from pydantic.dataclasses import dataclass

from api.interfaces.exchange_provider import ExchangeProvidersEnum
from api.interfaces.timeframe import Timeframe
from src.configuration.guard_config import GuardConfig


@dataclass
class Asset:
    keywords: list[str]
    base_ticker_symbol: str
    quote_ticker_symbol: str
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
    def ticker_symbol(self) -> str:
        return f"{self.base_ticker_symbol}_{self.quote_ticker_symbol}"

    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")
