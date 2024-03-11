#!/usr/bin/env python3

from pydantic import BaseModel, computed_field

from api.interfaces.exchange_provider import ExchangeProvidersEnum


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

    @computed_field
    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")
