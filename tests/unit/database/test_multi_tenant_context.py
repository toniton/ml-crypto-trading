import importlib
from unittest.mock import MagicMock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from src.database.dao.order_dao import OrderDao
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.database.tenant_context import TenantContext

migration_mod = importlib.import_module(
    "src.database.migrations.versions.v1a2b3c4d5e6_add_multi_tenant_user_id_and_rls"
)


class TestTenantContextResolution:
    def test_defaults_to_default_tenant(self, monkeypatch):
        monkeypatch.delenv(TenantContext.TENANT_ENV_VAR, raising=False)
        assert TenantContext.get_current_tenant_id() == TenantContext.DEFAULT_TENANT_ID

    def test_reads_tenant_from_environment(self, monkeypatch):
        monkeypatch.setenv(TenantContext.TENANT_ENV_VAR, "usr-env-01")
        assert TenantContext.get_current_tenant_id() == "usr-env-01"

    def test_tenant_scope_overrides_and_restores(self, monkeypatch):
        monkeypatch.setenv(TenantContext.TENANT_ENV_VAR, "usr-env-01")
        with TenantContext.scope("usr-scoped-99"):
            inside = TenantContext.get_current_tenant_id()
        assert inside == "usr-scoped-99" and TenantContext.get_current_tenant_id() == "usr-env-01"


class TestTenantScopedOrmModels:
    def test_order_dao_has_user_id_column_and_index(self):
        index_names = {idx.name for idx in OrderDao.__table__.indexes}
        assert "user_id" in OrderDao.__table__.columns and "ix_orders_user_id" in index_names

    def test_insert_uses_default_tenant_when_unset(self, monkeypatch):
        monkeypatch.delenv(TenantContext.TENANT_ENV_VAR, raising=False)
        engine = sa.create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        order = OrderDao(uuid="ord-default-1", provider_name="paper", ticker_symbol="BTC/USD")
        session.add(order)
        session.commit()
        assert order.user_id == TenantContext.DEFAULT_TENANT_ID

    def test_insert_uses_active_tenant_scope(self):
        engine = sa.create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        with TenantContext.scope("usr-10492"):
            order = OrderDao(uuid="ord-tenant-1", provider_name="paper", ticker_symbol="BTC/USD")
            session.add(order)
            session.commit()
        assert order.user_id == "usr-10492"


class TestPostgresRlsHook:
    def test_apply_rls_context_executes_set_config_for_postgres(self):
        mock_conn = MagicMock()
        mock_conn.dialect.name = "postgresql"
        SqlAlchemyDatabaseManager.apply_rls_context(mock_conn, tenant_id="usr-abc")
        assert mock_conn.execute.call_count == 1

    def test_apply_rls_context_skips_sqlite(self):
        mock_conn = MagicMock()
        mock_conn.dialect.name = "sqlite"
        SqlAlchemyDatabaseManager.apply_rls_context(mock_conn, tenant_id="usr-abc")
        mock_conn.execute.assert_not_called()


class TestMultiTenantMigration:
    def test_upgrade_and_downgrade_orders_table(self):
        engine = sa.create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE orders (id INTEGER PRIMARY KEY, uuid TEXT)"))

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration_mod.upgrade()

        upgraded_cols = {c["name"] for c in sa.inspect(engine).get_columns("orders")}

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration_mod.downgrade()

        downgraded_cols = {c["name"] for c in sa.inspect(engine).get_columns("orders")}
        assert "user_id" in upgraded_cols and "user_id" not in downgraded_cols
