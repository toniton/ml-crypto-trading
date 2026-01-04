import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from database.unit_of_work import UnitOfWork
from src.configuration.providers.database_config import DatabaseConfig


class DatabaseManager:
    BaseTableModel = declarative_base()

    def __init__(self):
        config = DatabaseConfig.get_instance()
        self.database_connection_endpoint = config.get_connection_endpoint()
        self.engine = None
        self._session_factory = None

    def _create_engine(self):
        if self.engine is None:
            self.engine = create_engine(self.database_connection_endpoint)
        return self.engine

    def _create_tables(self):
        self.BaseTableModel.metadata.create_all(self._create_engine())

    def _run_migrations(self):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        alembic_ini_path = os.path.join(project_root, "alembic.ini")
        migrations_path = os.path.join(project_root, "database", "migrations")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("script_location", migrations_path)
        command.upgrade(alembic_cfg, "head")

    def initialize(self) -> None:
        self._run_migrations()
        self._create_tables()
        engine = self._create_engine()
        self._session_factory = sessionmaker(bind=engine)

    def get_unit_of_work(self) -> UnitOfWork:
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager must be initialized before calling get_unit_of_work()")
        return UnitOfWork(self._session_factory())
