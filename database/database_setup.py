from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from configuration.providers.database_config import DatabaseConfig


class DatabaseSetup:
    BaseTableModel = declarative_base()

    def __init__(self):
        config = DatabaseConfig.get_instance()
        self.database_connection_endpoint = config.get_connection_endpoint()
        self.engine = None

    def create_engine(self):
        if self.engine is None:
            self.engine = create_engine(self.database_connection_endpoint)
        return self.engine

    def create_tables(self):
        self.BaseTableModel.metadata.create_all(self.create_engine())
