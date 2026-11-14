"""add multi-tenant user_id column and postgresql rls

Revision ID: v1a2b3c4d5e6
Revises: u1a2b3c4d5e6
Create Date: 2026-11-14 05:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v1a2b3c4d5e6"
down_revision: Union[str, None] = "u1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "conversations",
    "conversation_messages",
    "orders",
    "trades",
    "trading_decisions",
    "timeline_items",
    "runtime_incidents",
    "runtime_error_events",
    "vcs_commits",
    "vcs_blobs",
    "vcs_refs",
    "metric_definitions",
    "metric_samples",
    "backtest_sessions",
    "backtest_results",
    "experiments",
    "walk_forward_runs",
    "simulated_runs",
    "simulation_reports",
    "evidence_proposals",
    "promotion_records",
    "promotion_audit_events",
    "retention_runs",
    "retention_holds",
    "retention_audit_events",
    "llm_credentials",
)


class PostgresRlsHelper:
    @staticmethod
    def enable(table: str) -> None:
        policy = f"tenant_isolation_{table}"
        expr = "user_id = COALESCE(NULLIF(current_setting('app.current_user_id', true), ''), 'default')"
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {table}"))
        op.execute(sa.text(f"CREATE POLICY {policy} ON {table} USING ({expr}) WITH CHECK ({expr})"))

    @staticmethod
    def disable(table: str) -> None:
        policy = f"tenant_isolation_{table}"
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    is_postgres = bind.dialect.name == "postgresql"

    for table in TENANT_TABLES:
        if table not in existing_tables:
            continue

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "user_id" not in columns:
            op.add_column(
                table,
                sa.Column("user_id", sa.String(length=64), nullable=False, server_default="default"),
            )

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        index_name = f"ix_{table}_user_id"
        if index_name not in indexes:
            op.create_index(index_name, table, ["user_id"], unique=False)

        if is_postgres:
            PostgresRlsHelper.enable(table)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    is_postgres = bind.dialect.name == "postgresql"

    for table in TENANT_TABLES:
        if table not in existing_tables:
            continue

        if is_postgres:
            PostgresRlsHelper.disable(table)

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        index_name = f"ix_{table}_user_id"
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "user_id" in columns:
            op.drop_column(table, "user_id")
