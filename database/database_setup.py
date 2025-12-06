import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from src.configuration.providers.database_config import DatabaseConfig


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

    @staticmethod
    def run_migrations():
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        alembic_ini_path = os.path.join(project_root, "alembic.ini")
        migrations_path = os.path.join(project_root, "database", "migrations")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("script_location", migrations_path)
        command.upgrade(alembic_cfg, "head")
