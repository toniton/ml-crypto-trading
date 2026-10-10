"""Add metadata column to orders table

Revision ID: m1a2b3c4d5e6
Revises: l1a2b3c4d5e6
Create Date: 2026-10-10 23:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "m1a2b3c4d5e6"
down_revision: Union[str, None] = "l1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "orders" in tables:
        columns = [c["name"] for c in inspector.get_columns("orders")]
        if "metadata" not in columns:
            op.add_column("orders", sa.Column("metadata", json_type, server_default="{}", nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "orders" in tables:
        columns = [c["name"] for c in inspector.get_columns("orders")]
        if "metadata" in columns:
            op.drop_column("orders", "metadata")
