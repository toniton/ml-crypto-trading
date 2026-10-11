"""add walk_forward_runs table

Revision ID: n1a2b3c4d5e6
Revises: m1a2b3c4d5e6
Create Date: 2026-10-11 03:22:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "n1a2b3c4d5e6"
down_revision: Union[str, None] = "m1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "walk_forward_runs" not in tables:
        op.create_table(
            "walk_forward_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("ticker_symbol", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="RUNNING"),
            sa.Column("spec", json_type, nullable=True),
            sa.Column("summary", json_type, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_walk_forward_runs_ticker_symbol"),
            "walk_forward_runs",
            ["ticker_symbol"],
            unique=False,
        )
        op.create_index(
            op.f("ix_walk_forward_runs_created_at"),
            "walk_forward_runs",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "walk_forward_runs" in tables:
        op.drop_index(op.f("ix_walk_forward_runs_created_at"), table_name="walk_forward_runs")
        op.drop_index(op.f("ix_walk_forward_runs_ticker_symbol"), table_name="walk_forward_runs")
        op.drop_table("walk_forward_runs")
