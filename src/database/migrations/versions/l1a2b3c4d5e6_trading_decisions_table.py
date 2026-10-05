"""Add trading_decisions table

Revision ID: l1a2b3c4d5e6
Revises: k1a2b3c4d5e6
Create Date: 2026-10-05 08:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "l1a2b3c4d5e6"
down_revision: Union[str, None] = "k1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    op.create_table(
        "trading_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ticker_symbol", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trade_action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("commit_hash", sa.String(length=64), nullable=True),
        sa.Column("winning_strategy", sa.String(length=64), nullable=True),
        sa.Column("resulting_order_id", sa.String(length=64), nullable=True),
        sa.Column("market_snapshot", json_type, nullable=False, server_default="{}"),
        sa.Column("regime_snapshot", json_type, nullable=False, server_default="{}"),
        sa.Column("consensus_snapshot", json_type, nullable=False, server_default="{}"),
        sa.Column("sizing_snapshot", json_type, nullable=False, server_default="{}"),
        sa.Column("portfolio_snapshot", json_type, nullable=False, server_default="{}"),
        sa.Column("risk_evaluation", json_type, nullable=False, server_default="{}"),
        sa.Column("health_evaluation", json_type, nullable=True),
        sa.Column("metadata", json_type, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trading_decisions_timestamp"), "trading_decisions", ["timestamp"], unique=False)
    op.create_index(op.f("ix_trading_decisions_ticker_symbol"), "trading_decisions", ["ticker_symbol"], unique=False)
    op.create_index(op.f("ix_trading_decisions_exchange"), "trading_decisions", ["exchange"], unique=False)
    op.create_index(op.f("ix_trading_decisions_status"), "trading_decisions", ["status"], unique=False)
    op.create_index(op.f("ix_trading_decisions_commit_hash"), "trading_decisions", ["commit_hash"], unique=False)
    op.create_index(op.f("ix_trading_decisions_resulting_order_id"), "trading_decisions", ["resulting_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trading_decisions_resulting_order_id"), table_name="trading_decisions")
    op.drop_index(op.f("ix_trading_decisions_commit_hash"), table_name="trading_decisions")
    op.drop_index(op.f("ix_trading_decisions_status"), table_name="trading_decisions")
    op.drop_index(op.f("ix_trading_decisions_exchange"), table_name="trading_decisions")
    op.drop_index(op.f("ix_trading_decisions_ticker_symbol"), table_name="trading_decisions")
    op.drop_index(op.f("ix_trading_decisions_timestamp"), table_name="trading_decisions")
    op.drop_table("trading_decisions")
