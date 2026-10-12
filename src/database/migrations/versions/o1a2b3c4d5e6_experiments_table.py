"""add experiments table

Revision ID: o1a2b3c4d5e6
Revises: n1a2b3c4d5e6
Create Date: 2026-10-12 17:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "o1a2b3c4d5e6"
down_revision: Union[str, None] = "n1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "experiments" not in tables:
        op.create_table(
            "experiments",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("ticker_symbol", sa.String(length=32), nullable=False),
            sa.Column("branch_id", sa.String(length=64), nullable=False),
            sa.Column("base_commit_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
            sa.Column("spec", json_type, nullable=False),
            sa.Column("run_bindings", json_type, nullable=False),
            sa.Column("report", json_type, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_experiments_ticker_symbol"),
            "experiments",
            ["ticker_symbol"],
            unique=False,
        )
        op.create_index(
            op.f("ix_experiments_branch_id"),
            "experiments",
            ["branch_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_experiments_status"),
            "experiments",
            ["status"],
            unique=False,
        )
        op.create_index(
            op.f("ix_experiments_created_at"),
            "experiments",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "experiments" in tables:
        op.drop_index(op.f("ix_experiments_created_at"), table_name="experiments")
        op.drop_index(op.f("ix_experiments_status"), table_name="experiments")
        op.drop_index(op.f("ix_experiments_branch_id"), table_name="experiments")
        op.drop_index(op.f("ix_experiments_ticker_symbol"), table_name="experiments")
        op.drop_table("experiments")
