"""Add llm_credentials table with unique active model constraint

Revision ID: j1a2b3c4d5e6
Revises: i1a2b3c4d5e6
Create Date: 2026-10-01 19:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1a2b3c4d5e6"
down_revision: Union[str, None] = "i1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "llm_credentials" not in tables:
        op.create_table(
            "llm_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("model_id", sa.String(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("api_key", sa.String(), nullable=True),
            sa.Column("api_base_url", sa.String(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column(
                "created_timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "last_updated_timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_llm_credentials_model_id"),
            "llm_credentials",
            ["model_id"],
            unique=True,
        )
        op.create_index(
            "uq_llm_credentials_active",
            "llm_credentials",
            ["is_active"],
            unique=True,
            postgresql_where=sa.text("is_active = true"),
            sqlite_where=sa.text("is_active = 1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "llm_credentials" in tables:
        op.drop_table("llm_credentials")
