from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource, \
    YamlConfigSettingsSource
from src.trading.consensus.consensus_factor import ConsensusFactor


class LlmSettings(BaseModel):
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.0
    schedule: AssetSchedule = AssetSchedule.EVERY_MINUTE
    timeout: Optional[float] = None


class TradingConfig(BaseSettings):
    assets: list[Asset]
    consensus: ConsensusFactor
    dynamic_quantity: Optional[str] = None
    llm: LlmSettings = Field(default_factory=LlmSettings)

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
