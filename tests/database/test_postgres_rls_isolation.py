from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib
import os
from urllib.parse import urlparse, urlunparse

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.database.tenant_context import TenantContext

migration_mod = importlib.import_module(
    "src.database.migrations.versions.v1a2b3c4d5e6_add_multi_tenant_user_id_and_rls"
)

APP_ROLE = "rio_rls_test_app"
APP_PASSWORD = "rio_rls_test_password"
TEST_TABLE = "rls_test_orders"


def _build_role_url(admin_url: str, username: str, password: str) -> str:
    parsed = urlparse(admin_url)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{username}:{password}@{host}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


@pytest.fixture(scope="module")
def postgres_rls_engines():
    container = None
    admin_url = os.getenv("TEST_POSTGRES_ADMIN_URL", "").strip()

    if not admin_url:
        try:
            from testcontainers.community.postgres import PostgresContainer

            container = PostgresContainer("postgres:16-alpine")
            container.start()
            admin_url = container.get_connection_url(driver=None)
        except Exception as exc:
            if container is not None:
                container.stop()
            pytest.skip(f"PostgreSQL testcontainer unavailable: {exc}")

    admin_engine = sa.create_engine(admin_url)
    try:
        with admin_engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except OperationalError as exc:
        admin_engine.dispose()
        if container is not None:
            container.stop()
        pytest.skip(f"PostgreSQL not reachable for RLS integration tests: {exc}")

    app_url = _build_role_url(admin_url, APP_ROLE, APP_PASSWORD)
    app_engine = sa.create_engine(app_url)

    with admin_engine.begin() as conn:
        conn.execute(
            sa.text(
                f"DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
                f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; "
                f"END IF; "
                f"END $$;"
            )
        )
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {TEST_TABLE}"))
        conn.execute(
            sa.text(
                f"CREATE TABLE {TEST_TABLE} ("
                f"id SERIAL PRIMARY KEY, "
                f"uuid VARCHAR(64) NOT NULL, "
                f"user_id VARCHAR(64) NOT NULL DEFAULT 'default'"
                f")"
            )
        )
        policy = f"tenant_isolation_{TEST_TABLE}"
        expr = "user_id = COALESCE(NULLIF(current_setting('app.current_user_id', true), ''), 'default')"
        conn.execute(sa.text(f"ALTER TABLE {TEST_TABLE} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {TEST_TABLE} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"CREATE POLICY {policy} ON {TEST_TABLE} USING ({expr}) WITH CHECK ({expr})"))
        conn.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TEST_TABLE} TO {APP_ROLE}"))
        conn.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {TEST_TABLE}_id_seq TO {APP_ROLE}"))

    try:
        yield admin_engine, app_engine
    finally:
        app_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {TEST_TABLE}"))
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
        admin_engine.dispose()
        if container is not None:
            container.stop()


@contextmanager
def _tenant_session(app_engine, tenant_id: str):
    factory = sessionmaker(bind=app_engine)
    SqlAlchemyDatabaseManager._register_tenant_rls_hook(factory)
    with TenantContext.scope(tenant_id):
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class TestPostgresRlsIntegration:
    def test_restricted_role_passes_verification_and_admin_fails(self, postgres_rls_engines, monkeypatch):
        admin_engine, app_engine = postgres_rls_engines
        monkeypatch.setenv(TenantContext.TENANT_ENV_VAR, "usr-alpha")

        with app_engine.connect() as conn:
            SqlAlchemyDatabaseManager.verify_rls_role_enforced(conn)

        with admin_engine.connect() as conn:
            with pytest.raises(RuntimeError, match="NOSUPERUSER NOBYPASSRLS"):
                SqlAlchemyDatabaseManager.verify_rls_role_enforced(conn)

    def test_cross_tenant_read_update_delete_and_insert_isolation(self, postgres_rls_engines):
        _, app_engine = postgres_rls_engines

        with _tenant_session(app_engine, "usr-alpha") as session:
            session.execute(
                sa.text(f"INSERT INTO {TEST_TABLE} (uuid, user_id) VALUES ('ord-a1', 'usr-alpha')")
            )

        with _tenant_session(app_engine, "usr-beta") as session:
            session.execute(
                sa.text(f"INSERT INTO {TEST_TABLE} (uuid, user_id) VALUES ('ord-b1', 'usr-beta')")
            )

        with _tenant_session(app_engine, "usr-alpha") as session:
            rows = session.execute(sa.text(f"SELECT uuid, user_id FROM {TEST_TABLE}")).fetchall()
            assert rows == [("ord-a1", "usr-alpha")]

            updated = session.execute(
                sa.text(f"UPDATE {TEST_TABLE} SET uuid = 'hacked' WHERE uuid = 'ord-b1'")
            )
            assert updated.rowcount == 0

            deleted = session.execute(
                sa.text(f"DELETE FROM {TEST_TABLE} WHERE uuid = 'ord-b1'")
            )
            assert deleted.rowcount == 0

        with _tenant_session(app_engine, "usr-alpha") as session:
            with pytest.raises(ProgrammingError):
                session.execute(
                    sa.text(f"INSERT INTO {TEST_TABLE} (uuid, user_id) VALUES ('spoof', 'usr-beta')")
                )

    def test_concurrent_tenant_sessions_never_leak_rls_context(self, postgres_rls_engines):
        _, app_engine = postgres_rls_engines

        def _run_tenant_work(tenant_id: str, idx: int) -> tuple[str, list[str]]:
            order_uuid = f"conc-{tenant_id}-{idx}"
            with _tenant_session(app_engine, tenant_id) as session:
                session.execute(
                    sa.text(f"INSERT INTO {TEST_TABLE} (uuid, user_id) VALUES (:uuid, :uid)"),
                    {"uuid": order_uuid, "uid": tenant_id},
                )
                rows = session.execute(sa.text(f"SELECT user_id FROM {TEST_TABLE}")).fetchall()
                return tenant_id, [r[0] for r in rows]

        jobs = [("usr-alpha" if i % 2 == 0 else "usr-beta", i) for i in range(12)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda item: _run_tenant_work(*item), jobs))

        assert all(all(uid == expected_uid for uid in seen_uids) for expected_uid, seen_uids in results)
