from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource, \
    YamlConfigSettingsSource
from api.interfaces.asset import Asset


class AssetsConfig(BaseSettings):
    assets: list[Asset]

    _yaml_file: Optional[str] = ""
    model_config = SettingsConfigDict(
        yaml_file=_yaml_file,
        yaml_file_encoding="utf-8"
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
        return YamlConfigSettingsSource(settings_cls), CustomYamlConfigSettingsSource(init_settings, settings_cls)
