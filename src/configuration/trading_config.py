from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.interfaces.asset import Asset
from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource, \
    YamlConfigSettingsSource


class TradingConfig(BaseSettings):
    assets: list[Asset] = Field(
        description="List of trading assets.",
        json_schema_extra={"mutable": False},
    )
    dynamic_quantity: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Expression computing the quantity to buy. May reference indicators and the symbol `eq`.",
        json_schema_extra={"mutable": True},
    )

    @field_validator("assets")
    @classmethod
    def _validate_unique_asset_strategies(cls, assets: list[Asset]) -> list[Asset]:
        for asset in assets:
            strategies = asset.strategies or []
            names = [strategy.name for strategy in strategies]
            duplicates = {name for name in names if names.count(name) > 1}
            if duplicates:
                raise ValueError(
                    f"Duplicate strategy names for asset {asset.ticker_symbol}: "
                    f"{sorted(duplicates)}"
                )
        return assets

    _yaml_file: Optional[str] = ""
    model_config = SettingsConfigDict(
        yaml_file=_yaml_file,
        yaml_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
    ):
        return (init_settings,
                YamlConfigSettingsSource(settings_cls),
                CustomYamlConfigSettingsSource(init_settings, settings_cls))
