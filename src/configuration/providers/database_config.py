from dataclasses import dataclass

from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.base_config import BaseConfig


@dataclass
class DatabaseConfig(BaseConfig):
    def __init__(self, environment_config: EnvironmentConfig = None):
        if environment_config is None:
            environment_config = EnvironmentConfig()

        self.postgres_user = environment_config.postgres_user
        self.postgres_password = environment_config.postgres_password
        self.postgres_database = environment_config.postgres_database
        self.database_connection_host = environment_config.database_connection_host

    def get_connection_endpoint(self):
        return f"postgresql://" \
               f"{self.postgres_user}:" \
               f"{self.postgres_password.get_secret_value()}@" \
               f"{self.database_connection_host}/" \
               f"{self.postgres_database}"
