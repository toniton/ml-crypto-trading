from enum import Enum
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvEnum(str, Enum):
    STAGING = 'staging'
    PRODUCTION = 'production'


class EnvironmentConfig(BaseSettings):
    app_env: AppEnvEnum
    crypto_dot_com_exchange_api_key: Optional[str] = None
    crypto_dot_com_exchange_secret_key: Optional[str] = None
    coin_market_cap_api_key: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_database: Optional[str] = None
    postgres_password: Optional[SecretStr] = None

    model_config = SettingsConfigDict(env_file=".env")
