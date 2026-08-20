from __future__ import annotations

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource
from src.configuration.strategy_config import StrategyConfig


class StrategiesConfig(BaseSettings):
    strategies: list[StrategyConfig] = []

    @field_validator("strategies")
    @classmethod
    def _validate_unique_strategy_names(cls, strategies: list[StrategyConfig]) -> list[StrategyConfig]:
        names = [strategy.name for strategy in strategies]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"Duplicate predefined strategy names: {sorted(duplicates)}")
        return strategies

    _yaml_file: Optional[str | tuple[str, str]] = "src/configuration/strategies.yaml"
    model_config = SettingsConfigDict(
        yaml_file=_yaml_file,
        yaml_file_encoding="utf-8",
        env_file=".env",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra='ignore'
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
        return (
            init_settings, env_settings, dotenv_settings,
            CustomYamlConfigSettingsSource(init_settings, settings_cls),
            YamlConfigSettingsSource(settings_cls)
        )
