from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvEnum(str, Enum):
    STAGING = 'staging'
    PRODUCTION = 'production'


class ExchangeCredentials(BaseModel):
    api_key: Optional[str] = None
    secret_key: Optional[SecretStr] = None

    model_config = SettingsConfigDict(extra='ignore')


class CCXTProviderSettings(BaseModel):
    binance: ExchangeCredentials = Field(default_factory=ExchangeCredentials)
    kraken: ExchangeCredentials = Field(default_factory=ExchangeCredentials)
    coinbase: ExchangeCredentials = Field(default_factory=ExchangeCredentials)
    bybit: ExchangeCredentials = Field(default_factory=ExchangeCredentials)
    kucoin: ExchangeCredentials = Field(default_factory=ExchangeCredentials)

    model_config = SettingsConfigDict(extra='ignore')

    def get_provider_credentials(self, provider: Any) -> Optional[ExchangeCredentials]:
        key = provider.name if isinstance(provider, Enum) else str(provider).upper()
        if "BINANCE" in key:
            return self.binance
        if "KRAKEN" in key:
            return self.kraken
        if "COINBASE" in key:
            return self.coinbase
        if "BYBIT" in key:
            return self.bybit
        if "KUCOIN" in key:
            return self.kucoin
        return None


class EnvironmentConfig(BaseSettings):
    app_env: AppEnvEnum
    database_connection_host: str = Field()
    crypto_dot_com: Optional[ExchangeCredentials] = None
    postgres_user: Optional[str] = None
    postgres_database: Optional[str] = None
    postgres_password: Optional[SecretStr] = None
    log_dir: str = Field(default='.')
    log_level: Optional[str] = Field(default=None)

    # Nested CCXT provider settings
    ccxt_providers: CCXTProviderSettings = Field(default_factory=CCXTProviderSettings)

    @model_validator(mode='after')
    def set_default_log_level(self) -> 'EnvironmentConfig':
        if self.log_level is None:
            if self.app_env == AppEnvEnum.STAGING:
                self.log_level = 'DEBUG'
            else:
                self.log_level = 'INFO'
        return self

    model_config = SettingsConfigDict(env_file=".env", extra='ignore', env_nested_delimiter='__')
