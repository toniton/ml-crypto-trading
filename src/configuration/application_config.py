from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from src.configuration.environment_config import AppEnvEnum
from src.configuration.helpers.application_helper import ApplicationHelper
from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource


class ApplicationConfig(BaseSettings):
    crypto_dot_com_exchange_rest_endpoint: Optional[str] = Field(default=None)
    crypto_dot_com_exchange_websocket_endpoint: Optional[str] = Field(default=None)
    coin_market_cap_rest_endpoint: Optional[str] = Field(default=None)
    database_connection_host: str = Field()

    _yaml_file: Optional[str] = (
        ApplicationHelper.get_env_path(AppEnvEnum.STAGING),
        ApplicationHelper.get_env_path(AppEnvEnum.PRODUCTION)
    )
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
        return YamlConfigSettingsSource(settings_cls), CustomYamlConfigSettingsSource(init_settings, settings_cls),
