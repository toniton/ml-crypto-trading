#!/usr/bin/env python3
import warnings
from typing import Optional

from pydantic import Field, computed_field, model_validator
from pydantic.dataclasses import dataclass

from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.configuration.guard_config import GuardConfig
from src.configuration.strategy_config import StrategyConfig
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor


@dataclass(frozen=True)
class Asset:
    base_ticker_symbol: str = Field(
        description="Base currency of the trading pair (e.g. BTC).",
        json_schema_extra={"mutable": False},
    )
    quote_ticker_symbol: str = Field(
        description="Quote currency of the trading pair (e.g. USD).",
        json_schema_extra={"mutable": False},
    )
    quote_decimals: int = Field(
        description="Number of decimals used for quote amounts.",
        json_schema_extra={"mutable": False},
    )
    name: str = Field(
        description="Human-readable display name of the asset.",
        json_schema_extra={"mutable": False},
    )
    exchange: ExchangeProvidersEnum = Field(
        description="Exchange the asset is traded on.",
        json_schema_extra={"mutable": False},
    )
    min_quantity: float = Field(
        gt=0,
        description="Minimum tradeable quantity for this asset.",
        json_schema_extra={"mutable": True},
    )
    quantity_decimals: int = Field(
        description="Number of decimals used for quantities.",
        json_schema_extra={"mutable": False},
    )
    schedule: AssetSchedule = Field(
        description="Trading cadence for this asset: 0=second, 1=minute, 2=hour, 3=day, 4=week, 5=month.",
        json_schema_extra={"mutable": True},
    )
    candles_timeframe: Timeframe = Field(
        description="Candle timeframe used to feed the strategy (e.g. MIN1).",
        json_schema_extra={"mutable": False},
    )
    guard_config: Optional[GuardConfig] = Field(
        default=None,
        description="Risk guard configuration for this asset.",
        json_schema_extra={"mutable": True},
    )
    keywords: Optional[list[str]] = Field(
        default=None,
        description="Optional keywords for asset discovery.",
        json_schema_extra={"mutable": False},
    )
    separator: Optional[str] = Field(
        default=None,
        description="Separator used in ticker symbol (default '_').",
        json_schema_extra={"mutable": False},
    )
    strategies: Optional[list[StrategyConfig]] = Field(
        default=None,
        description="Trading strategies for this asset.",
        json_schema_extra={"mutable": True},
    )
    consensus: Optional[ConsensusFactor] = Field(
        default=None,
        description="Consensus thresholds for this asset.",
        json_schema_extra={"mutable": True},
    )

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
