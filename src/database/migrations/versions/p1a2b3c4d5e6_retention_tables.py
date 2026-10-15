"""add retention tables

Revision ID: p1a2b3c4d5e6
Revises: o1a2b3c4d5e6
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "p1a2b3c4d5e6"
down_revision: Union[str, None] = "o1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> list[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.get_table_names()


def upgrade() -> None:
    tables = _tables()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "retention_runs" not in tables:
        op.create_table(
            "retention_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("trigger", sa.String(length=16), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("policy_version", sa.String(length=32), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("categories", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("storage_reclaimed_bytes", sa.BigInteger(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_retention_runs_status"), "retention_runs", ["status"])
        op.create_index(op.f("ix_retention_runs_started_at"), "retention_runs", ["started_at"])

    if "retention_audit_events" not in tables:
        op.create_table(
            "retention_audit_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("policy_id", sa.String(length=64), nullable=True),
            sa.Column("actor", sa.String(length=64), nullable=True),
            sa.Column("old_value", json_type, nullable=True),
            sa.Column("new_value", json_type, nullable=True),
            sa.Column("run_id", sa.String(length=36), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_retention_audit_events_event_type"), "retention_audit_events", ["event_type"])
        op.create_index(op.f("ix_retention_audit_events_policy_id"), "retention_audit_events", ["policy_id"])
        op.create_index(op.f("ix_retention_audit_events_run_id"), "retention_audit_events", ["run_id"])
        op.create_index(op.f("ix_retention_audit_events_created_at"), "retention_audit_events", ["created_at"])

    if "retention_holds" not in tables:
        op.create_table(
            "retention_holds",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("data_category", sa.String(length=32), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_retention_holds_data_category"), "retention_holds", ["data_category"])
        op.create_index(op.f("ix_retention_holds_active"), "retention_holds", ["active"])


def downgrade() -> None:
    tables = _tables()

    if "retention_holds" in tables:
        op.drop_index(op.f("ix_retention_holds_active"), table_name="retention_holds")
        op.drop_index(op.f("ix_retention_holds_data_category"), table_name="retention_holds")
        op.drop_table("retention_holds")

    if "retention_audit_events" in tables:
        op.drop_index(op.f("ix_retention_audit_events_created_at"), table_name="retention_audit_events")
        op.drop_index(op.f("ix_retention_audit_events_run_id"), table_name="retention_audit_events")
        op.drop_index(op.f("ix_retention_audit_events_policy_id"), table_name="retention_audit_events")
        op.drop_index(op.f("ix_retention_audit_events_event_type"), table_name="retention_audit_events")
        op.drop_table("retention_audit_events")

    if "retention_runs" in tables:
        op.drop_index(op.f("ix_retention_runs_started_at"), table_name="retention_runs")
        op.drop_index(op.f("ix_retention_runs_status"), table_name="retention_runs")
        op.drop_table("retention_runs")
