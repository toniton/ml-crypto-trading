from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource
from src.configuration.providers.cryptodotcom_config import CryptoDotComConfig


class ExchangesConfig(BaseSettings):
    crypto_dot_com: CryptoDotComConfig = CryptoDotComConfig(
        secret_key=None, api_key=None, rest_endpoint=None, websocket_endpoint=None
    )

    _yaml_file: Optional[str | tuple[str, str]] = "src/configuration/exchanges.yaml"
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
            env_settings, dotenv_settings, YamlConfigSettingsSource(settings_cls),
            CustomYamlConfigSettingsSource(init_settings, settings_cls)
        )
