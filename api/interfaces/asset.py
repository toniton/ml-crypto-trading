#!/usr/bin/env python3
import warnings
from typing import Optional

from pydantic import computed_field, model_validator
from pydantic.dataclasses import dataclass

from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.configuration.guard_config import GuardConfig
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


@dataclass(frozen=True)
class Asset:
    base_ticker_symbol: str
    quote_ticker_symbol: str
    quote_decimals: int
    name: str
    exchange: ExchangeProvidersEnum
    min_quantity: float
    quantity_decimals: int
    schedule: AssetSchedule
    candles_timeframe: Timeframe
    guard_config: Optional[GuardConfig] = None
    keywords: Optional[list[str]] = None
    separator: Optional[str] = None

    @computed_field
    @property
    def ticker_symbol(self) -> str:
        separator = self.separator if self.separator is not None else "_"
        return f"{self.base_ticker_symbol}{separator}{self.quote_ticker_symbol}"

    @property
    def key(self) -> int:
        return hash(f"{self.ticker_symbol}-{self.exchange.value}")

    @property
    def decimal_places(self) -> float:
        """Deprecated: use :attr:`quote_decimals` instead."""
        return self.quote_decimals

    @model_validator(mode="before")
    @classmethod
    def _map_decimal_places_alias(cls, data) -> "dict | object":
        kwargs = getattr(data, "kwargs", None)
        mapping = kwargs if isinstance(kwargs, dict) else (data if isinstance(data, dict) else None)
        if isinstance(mapping, dict) and "decimal_places" in mapping and "quote_decimals" not in mapping:
            warnings.warn(
                "Asset.decimal_places is deprecated; use 'quote_decimals' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            mapping["quote_decimals"] = mapping.pop("decimal_places")
        return data
