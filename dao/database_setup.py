from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from configuration.application_config import ApplicationConfig
from configuration.environment_config import EnvironmentConfig


class DatabaseSetup:
    BaseTableModel = declarative_base()

    def __init__(self, environment_config: EnvironmentConfig, application_config: ApplicationConfig):
        self.postgres_user = environment_config.postgres_user
        self.postgres_password = environment_config.postgres_password
        self.postgres_database = environment_config.postgres_database
        self.database_connection_host = application_config.database_connection_host
        self.engine = None

    def create_engine(self):
        database_connection_endpoint = f"postgresql://" \
                                       f"{self.postgres_user}:" \
                                       f"{self.postgres_password.get_secret_value()}@" \
                                       f"{self.database_connection_host}/" \
                                       f"{self.postgres_database}"
        if self.engine is None:
            self.engine = create_engine(database_connection_endpoint)
        return self.engine

    def create_tables(self):
        self.BaseTableModel.metadata.create_all(self.create_engine())