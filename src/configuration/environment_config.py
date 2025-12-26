from enum import Enum
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvEnum(str, Enum):
    STAGING = 'staging'
    PRODUCTION = 'production'


class EnvironmentConfig(BaseSettings):
    app_env: AppEnvEnum
    database_connection_host: str = Field()
    crypto_dot_com__api_key: Optional[str] = None
    crypto_dot_com__secret_key: Optional[str] = None
    coin_market_cap_api_key: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_database: Optional[str] = None
    postgres_password: Optional[SecretStr] = None

    model_config = SettingsConfigDict(env_file=".env")
