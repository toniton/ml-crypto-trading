from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvEnum(str, Enum):
    staging = 'staging'
    production = 'production'


class EnvironmentConfig(BaseSettings):
    app_env: AppEnvEnum
    crypto_dot_com_exchange_api_key: str
    crypto_dot_com_exchange_secret_key: str

    model_config = SettingsConfigDict(env_file=".env")
