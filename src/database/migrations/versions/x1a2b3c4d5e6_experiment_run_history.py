"""add run_history column to experiments table

Revision ID: x1a2b3c4d5e6
Revises: w1a2b3c4d5e6
Create Date: 2026-11-27 16:51:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "x1a2b3c4d5e6"
down_revision: Union[str, None] = "w1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "experiments" not in tables:
        return

    existing_cols = {col["name"] for col in inspector.get_columns("experiments")}
    if "run_history" not in existing_cols:
        json_type = sa.JSON().with_variant(JSONB, "postgresql")
        op.add_column(
            "experiments",
            sa.Column(
                "run_history",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "experiments" not in tables:
        return

    existing_cols = {col["name"] for col in inspector.get_columns("experiments")}
    if "run_history" in existing_cols:
        op.drop_column("experiments", "run_history")
