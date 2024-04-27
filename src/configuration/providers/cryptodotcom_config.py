from dataclasses import dataclass

from src.configuration.application_config import ApplicationConfig
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.providers.base_config import BaseConfig


@dataclass
class CryptodotcomConfig(BaseConfig):
    def __init__(self, app_config: ApplicationConfig = None, env_config: EnvironmentConfig = None):
        self.base_url = app_config.crypto_dot_com_exchange_rest_endpoint
        self.websocket_url = app_config.crypto_dot_com_exchange_websocket_endpoint
        self.api_key = env_config.crypto_dot_com_exchange_api_key
        self.secret_key = env_config.crypto_dot_com_exchange_secret_key
