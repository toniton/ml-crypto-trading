"""add backtest execution durability columns and indexes

Revision ID: r1a2b3c4d5e6
Revises: q1a2b3c4d5e6
Create Date: 2026-10-23 20:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r1a2b3c4d5e6"
down_revision: Union[str, None] = "q1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "backtest_sessions" in tables:
        columns = [c["name"] for c in inspector.get_columns("backtest_sessions")]

        if "worker_id" not in columns:
            op.add_column("backtest_sessions", sa.Column("worker_id", sa.String(length=64), nullable=True))
        if "started_at" not in columns:
            op.add_column("backtest_sessions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        if "completed_at" not in columns:
            op.add_column("backtest_sessions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        if "heartbeat_at" not in columns:
            op.add_column("backtest_sessions", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        if "lease_expires_at" not in columns:
            op.add_column("backtest_sessions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        if "error_message" not in columns:
            op.add_column("backtest_sessions", sa.Column("error_message", sa.Text(), nullable=True))

        indexes = [ix["name"] for ix in inspector.get_indexes("backtest_sessions")]
        if "ix_backtest_sessions_status" not in indexes:
            op.create_index(op.f("ix_backtest_sessions_status"), "backtest_sessions", ["status"], unique=False)
        if "ix_backtest_sessions_lease_expires_at" not in indexes:
            op.create_index(
                op.f("ix_backtest_sessions_lease_expires_at"),
                "backtest_sessions",
                ["lease_expires_at"],
                unique=False,
            )
        if "ix_backtest_sessions_heartbeat_at" not in indexes:
            op.create_index(
                op.f("ix_backtest_sessions_heartbeat_at"),
                "backtest_sessions",
                ["heartbeat_at"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "backtest_sessions" in tables:
        indexes = [ix["name"] for ix in inspector.get_indexes("backtest_sessions")]
        if "ix_backtest_sessions_heartbeat_at" in indexes:
            op.drop_index(op.f("ix_backtest_sessions_heartbeat_at"), table_name="backtest_sessions")
        if "ix_backtest_sessions_lease_expires_at" in indexes:
            op.drop_index(op.f("ix_backtest_sessions_lease_expires_at"), table_name="backtest_sessions")
        if "ix_backtest_sessions_status" in indexes:
            op.drop_index(op.f("ix_backtest_sessions_status"), table_name="backtest_sessions")

        columns = [c["name"] for c in inspector.get_columns("backtest_sessions")]
        if "error_message" in columns:
            op.drop_column("backtest_sessions", "error_message")
        if "lease_expires_at" in columns:
            op.drop_column("backtest_sessions", "lease_expires_at")
        if "heartbeat_at" in columns:
            op.drop_column("backtest_sessions", "heartbeat_at")
        if "completed_at" in columns:
            op.drop_column("backtest_sessions", "completed_at")
        if "started_at" in columns:
            op.drop_column("backtest_sessions", "started_at")
        if "worker_id" in columns:
            op.drop_column("backtest_sessions", "worker_id")
