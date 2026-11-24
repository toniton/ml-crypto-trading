"""create scorecard_snapshots table

Revision ID: w1a2b3c4d5e6
Revises: v1a2b3c4d5e6
Create Date: 2026-11-22 14:25:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w1a2b3c4d5e6"
down_revision: Union[str, None] = "v1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scorecard_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("branch", sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("commit_hash", sa.String(length=64), nullable=True),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("current_stage", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("drifted", sa.Boolean(), nullable=True),
        sa.Column("live_return_pct", sa.Float(), nullable=True),
        sa.Column("oos_return_pct", sa.Float(), nullable=True),
        sa.Column("backtest_return_pct", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_scorecard_snapshots_symbol", "scorecard_snapshots", ["symbol"])
    op.create_index("ix_scorecard_snapshots_commit_hash", "scorecard_snapshots", ["commit_hash"])
    op.create_index("ix_scorecard_snapshots_created_at", "scorecard_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_scorecard_snapshots_created_at", table_name="scorecard_snapshots")
    op.drop_index("ix_scorecard_snapshots_commit_hash", table_name="scorecard_snapshots")
    op.drop_index("ix_scorecard_snapshots_symbol", table_name="scorecard_snapshots")
    op.drop_table("scorecard_snapshots")
