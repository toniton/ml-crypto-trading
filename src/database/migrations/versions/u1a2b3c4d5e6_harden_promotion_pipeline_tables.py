"""harden promotion pipeline tables

Revision ID: u1a2b3c4d5e6
Revises: t1a2b3c4d5e6
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "u1a2b3c4d5e6"
down_revision: Union[str, None] = "t1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    if "simulated_runs" in tables:
        sim_cols = [c["name"] for c in inspector.get_columns("simulated_runs")]
        if "effective_config" not in sim_cols:
            op.add_column("simulated_runs", sa.Column("effective_config", json_type, nullable=True))
        if "baseline_run_id" not in sim_cols:
            op.add_column("simulated_runs", sa.Column("baseline_run_id", sa.String(length=64), nullable=True))

    if "promotion_records" in tables:
        promo_cols = [c["name"] for c in inspector.get_columns("promotion_records")]
        if "report_id" not in promo_cols:
            op.add_column("promotion_records", sa.Column("report_id", sa.String(length=64), nullable=True))
        if "run_id" not in promo_cols:
            op.add_column("promotion_records", sa.Column("run_id", sa.String(length=64), nullable=True))
        if "config_hash" not in promo_cols:
            op.add_column("promotion_records", sa.Column("config_hash", sa.String(length=128), nullable=True))


def downgrade() -> None:
    pass
