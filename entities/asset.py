#!/usr/bin/env python3

from pydantic import BaseModel, computed_field

from entities.exchange_provider import ExchangeProvidersEnum


class Asset(BaseModel):
    keywords: list[str]
    ticker_symbol: str
    name: str
    current_price: float
    market_cap: float
    exchange: ExchangeProvidersEnum
    sector: str
    industry: str

    @computed_field
    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")
