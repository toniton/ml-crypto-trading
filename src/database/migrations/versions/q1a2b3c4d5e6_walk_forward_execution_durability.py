"""add walk forward execution durability columns and indexes

Revision ID: q1a2b3c4d5e6
Revises: p1a2b3c4d5e6
Create Date: 2026-10-23 19:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q1a2b3c4d5e6"
down_revision: Union[str, None] = "p1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "walk_forward_runs" in tables:
        columns = [c["name"] for c in inspector.get_columns("walk_forward_runs")]

        if "worker_id" not in columns:
            op.add_column("walk_forward_runs", sa.Column("worker_id", sa.String(length=64), nullable=True))
        if "started_at" not in columns:
            op.add_column("walk_forward_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        if "completed_at" not in columns:
            op.add_column("walk_forward_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        if "heartbeat_at" not in columns:
            op.add_column("walk_forward_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        if "lease_expires_at" not in columns:
            op.add_column("walk_forward_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        if "error_message" not in columns:
            op.add_column("walk_forward_runs", sa.Column("error_message", sa.Text(), nullable=True))

        indexes = [ix["name"] for ix in inspector.get_indexes("walk_forward_runs")]
        if "ix_walk_forward_runs_status" not in indexes:
            op.create_index(op.f("ix_walk_forward_runs_status"), "walk_forward_runs", ["status"], unique=False)
        if "ix_walk_forward_runs_lease_expires_at" not in indexes:
            op.create_index(
                op.f("ix_walk_forward_runs_lease_expires_at"),
                "walk_forward_runs",
                ["lease_expires_at"],
                unique=False,
            )
        if "ix_walk_forward_runs_heartbeat_at" not in indexes:
            op.create_index(
                op.f("ix_walk_forward_runs_heartbeat_at"),
                "walk_forward_runs",
                ["heartbeat_at"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "walk_forward_runs" in tables:
        indexes = [ix["name"] for ix in inspector.get_indexes("walk_forward_runs")]
        if "ix_walk_forward_runs_heartbeat_at" in indexes:
            op.drop_index(op.f("ix_walk_forward_runs_heartbeat_at"), table_name="walk_forward_runs")
        if "ix_walk_forward_runs_lease_expires_at" in indexes:
            op.drop_index(op.f("ix_walk_forward_runs_lease_expires_at"), table_name="walk_forward_runs")
        if "ix_walk_forward_runs_status" in indexes:
            op.drop_index(op.f("ix_walk_forward_runs_status"), table_name="walk_forward_runs")

        columns = [c["name"] for c in inspector.get_columns("walk_forward_runs")]
        if "error_message" in columns:
            op.drop_column("walk_forward_runs", "error_message")
        if "lease_expires_at" in columns:
            op.drop_column("walk_forward_runs", "lease_expires_at")
        if "heartbeat_at" in columns:
            op.drop_column("walk_forward_runs", "heartbeat_at")
        if "completed_at" in columns:
            op.drop_column("walk_forward_runs", "completed_at")
        if "started_at" in columns:
            op.drop_column("walk_forward_runs", "started_at")
        if "worker_id" in columns:
            op.drop_column("walk_forward_runs", "worker_id")
