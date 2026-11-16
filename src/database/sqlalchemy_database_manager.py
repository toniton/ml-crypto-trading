import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from src.core.interfaces.database_manager import DatabaseManager
from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.database.tenant_context import TenantContext, TenantScopedMixin
from src.configuration.providers.database_config import DatabaseConfig
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.logging.factory import LoggingFactory


class SqlAlchemyDatabaseManager(DatabaseManager, ApplicationLoggingMixin):
    BaseTableModel = declarative_base(cls=TenantScopedMixin)

    def __init__(self):
        config = DatabaseConfig.get_instance()
        self.database_connection_endpoint = config.get_connection_endpoint()
        self.pool_size = getattr(config, "postgres_pool_size", 20)
        self.max_overflow = getattr(config, "postgres_max_overflow", 20)
        self.pool_timeout = getattr(config, "postgres_pool_timeout", 30.0)
        self.pool_recycle = getattr(config, "postgres_pool_recycle", 1800)
        self.engine = None
        self._session_factory = None

    def get_engine(self):
        if self.engine is None:
            if "sqlite" in self.database_connection_endpoint:
                self.engine = create_engine(self.database_connection_endpoint)
            else:
                self.engine = create_engine(
                    self.database_connection_endpoint,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=True,
                )
        return self.engine

    def _create_tables(self):
        self.BaseTableModel.metadata.create_all(self.get_engine())

    @staticmethod
    def _build_alembic_config() -> Config:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        alembic_ini_path = os.path.join(project_root, "alembic.ini")
        migrations_path = os.path.join(project_root, "src", "database", "migrations")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("script_location", migrations_path)
        return alembic_cfg

    def _run_migrations(self):
        command.upgrade(self._build_alembic_config(), "head")

    def initialize(self) -> None:
        skip_migrations = os.getenv("SKIP_MIGRATIONS", "").strip().lower() == "true"
        if skip_migrations:
            self.app_logger.info("Skipping Alembic migrations because SKIP_MIGRATIONS=true.")
        else:
            self._run_migrations()
            self._create_tables()

        engine = self.get_engine()
        with engine.connect() as connection:
            self.verify_rls_role_enforced(connection)
            if skip_migrations:
                self.verify_schema_compatibility(connection)
        self._session_factory = sessionmaker(bind=engine)
        self._register_tenant_rls_hook(self._session_factory)

    @classmethod
    def verify_schema_compatibility(cls, connection, alembic_cfg: Config | None = None) -> None:
        """Fail fast if the PostgreSQL schema is not at the expected Alembic head revision."""
        if connection.dialect.name != "postgresql":
            return
        cfg = alembic_cfg or cls._build_alembic_config()
        expected_heads = set(ScriptDirectory.from_config(cfg).get_heads())
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
        if current_heads != expected_heads:
            raise RuntimeError(
                f"Database schema revision mismatch: current={sorted(current_heads)}, "
                f"expected={sorted(expected_heads)}. Run database migrations before starting tenant containers."
            )

    @classmethod
    def verify_rls_role_enforced(cls, connection) -> None:
        """Ensure PostgreSQL runtime connections do not bypass Row-Level Security."""
        if connection.dialect.name != "postgresql":
            return
        row = connection.execute(
            text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).fetchone()
        if not row:
            return
        role_name, is_superuser, has_bypassrls = row[0], bool(row[1]), bool(row[2])
        if not (is_superuser or has_bypassrls):
            return

        require_rls = os.getenv("REQUIRE_RLS_ENFORCEMENT", "").strip().lower() == "true"
        tenant_id = TenantContext.get_current_tenant_id()
        if require_rls or tenant_id != TenantContext.DEFAULT_TENANT_ID:
            raise RuntimeError(
                f"PostgreSQL role '{role_name}' has SUPERUSER or BYPASSRLS privileges, "
                f"which disables Row-Level Security for tenant '{tenant_id}'. "
                "Connect with a dedicated least-privileged role (NOSUPERUSER NOBYPASSRLS)."
            )
        LoggingFactory.get_application_logger(cls.__name__).warning(
            "PostgreSQL role '%s' has SUPERUSER or BYPASSRLS privileges; RLS is bypassed in local default mode.",
            role_name,
        )

    @staticmethod
    def apply_rls_context(connection, tenant_id: str | None = None) -> None:
        if connection.dialect.name != "postgresql":
            return
        resolved_tenant = tenant_id or TenantContext.get_current_tenant_id()
        connection.execute(
            text("SELECT set_config('app.current_user_id', :tenant_id, true)"),
            {"tenant_id": resolved_tenant},
        )

    @classmethod
    def _register_tenant_rls_hook(cls, session_factory: sessionmaker) -> None:
        @event.listens_for(session_factory, "after_begin")
        def _on_after_begin(_session, _transaction, connection) -> None:
            cls.apply_rls_context(connection)

    def get_unit_of_work(self) -> SqlAlchemyUnitOfWork:
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager must be initialized before calling get_unit_of_work()")
        return SqlAlchemyUnitOfWork(self._session_factory())
