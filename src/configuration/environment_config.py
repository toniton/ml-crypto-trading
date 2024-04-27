from enum import Enum

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvEnum(str, Enum):
    staging = 'staging'
    production = 'production'


class EnvironmentConfig(BaseSettings):
    app_env: AppEnvEnum
    crypto_dot_com_exchange_api_key: str
    crypto_dot_com_exchange_secret_key: str
    coin_market_cap_api_key: str
    postgres_user: str
    postgres_database: str
    postgres_password: SecretStr

    model_config = SettingsConfigDict(env_file=".env")
