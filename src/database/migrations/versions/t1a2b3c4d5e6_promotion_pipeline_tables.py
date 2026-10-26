"""add promotion pipeline tables

Revision ID: t1a2b3c4d5e6
Revises: s1a2b3c4d5e6
Create Date: 2026-10-25 15:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "t1a2b3c4d5e6"
down_revision: Union[str, None] = "s1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "simulated_runs" not in tables:
        op.create_table(
            "simulated_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_commit", sa.String(length=64), nullable=False),
            sa.Column("config_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("market_data_spec", json_type, nullable=False),
            sa.Column("execution_spec", json_type, nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_simulated_runs_experiment_id"), "simulated_runs", ["experiment_id"], unique=False)
        op.create_index(op.f("ix_simulated_runs_candidate_id"), "simulated_runs", ["candidate_id"], unique=False)
        op.create_index(op.f("ix_simulated_runs_status"), "simulated_runs", ["status"], unique=False)
        op.create_index(op.f("ix_simulated_runs_created_at"), "simulated_runs", ["created_at"], unique=False)

    if "simulation_reports" not in tables:
        op.create_table(
            "simulation_reports",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("config_hash", sa.String(length=64), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("summary_metrics", json_type, nullable=False),
            sa.Column("report_payload", json_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_simulation_reports_run_id"), "simulation_reports", ["run_id"], unique=True)
        op.create_index(op.f("ix_simulation_reports_decision"), "simulation_reports", ["decision"], unique=False)
        op.create_index(op.f("ix_simulation_reports_created_at"), "simulation_reports", ["created_at"], unique=False)

    if "promotion_records" not in tables:
        op.create_table(
            "promotion_records",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("idempotency_key", sa.String(length=64), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("source_commit", sa.String(length=64), nullable=False),
            sa.Column("target_ref", sa.String(length=64), nullable=False),
            sa.Column("merge_commit_hash", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("approver", sa.String(length=64), nullable=False),
            sa.Column("approval_notes", sa.Text(), nullable=True),
            sa.Column("gate_results", json_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_promotion_records_idempotency_key"), "promotion_records", ["idempotency_key"], unique=True)
        op.create_index(op.f("ix_promotion_records_experiment_id"), "promotion_records", ["experiment_id"], unique=False)
        op.create_index(op.f("ix_promotion_records_status"), "promotion_records", ["status"], unique=False)
        op.create_index(op.f("ix_promotion_records_created_at"), "promotion_records", ["created_at"], unique=False)

    if "promotion_audit_events" not in tables:
        op.create_table(
            "promotion_audit_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("promotion_id", sa.String(length=64), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("from_state", sa.String(length=32), nullable=True),
            sa.Column("to_state", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=64), nullable=False),
            sa.Column("payload", json_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_promotion_audit_events_promotion_id"), "promotion_audit_events", ["promotion_id"], unique=False)
        op.create_index(op.f("ix_promotion_audit_events_event_type"), "promotion_audit_events", ["event_type"], unique=False)
        op.create_index(op.f("ix_promotion_audit_events_to_state"), "promotion_audit_events", ["to_state"], unique=False)
        op.create_index(op.f("ix_promotion_audit_events_created_at"), "promotion_audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    for table_name in ("promotion_audit_events", "promotion_records", "simulation_reports", "simulated_runs"):
        if table_name in tables:
            indexes = [ix["name"] for ix in inspector.get_indexes(table_name)]
            for ix in indexes:
                op.drop_index(op.f(ix), table_name=table_name)
            op.drop_table(table_name)
