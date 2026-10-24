"""add evidence_proposals table

Revision ID: s1a2b3c4d5e6
Revises: r1a2b3c4d5e6
Create Date: 2026-10-23 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s1a2b3c4d5e6"
down_revision: Union[str, None] = "r1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "evidence_proposals" not in tables:
        op.create_table(
            "evidence_proposals",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=True),
            sa.Column("ticker_symbol", sa.String(length=32), nullable=False),
            sa.Column("baseline_commit", sa.String(length=64), nullable=False),
            sa.Column("candidate_commit", sa.String(length=64), nullable=True),
            sa.Column("candidate_id", sa.String(length=64), nullable=True),
            sa.Column("evidence_status", sa.String(length=32), nullable=False),
            sa.Column("recommendation", sa.String(length=32), nullable=False),
            sa.Column("calculation_version", sa.String(length=16), nullable=False, server_default="1.0.0"),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_evidence_proposals_experiment_id"),
            "evidence_proposals",
            ["experiment_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_evidence_proposals_ticker_symbol"),
            "evidence_proposals",
            ["ticker_symbol"],
            unique=False,
        )
        op.create_index(
            op.f("ix_evidence_proposals_evidence_status"),
            "evidence_proposals",
            ["evidence_status"],
            unique=False,
        )
        op.create_index(
            op.f("ix_evidence_proposals_recommendation"),
            "evidence_proposals",
            ["recommendation"],
            unique=False,
        )
        op.create_index(
            op.f("ix_evidence_proposals_created_at"),
            "evidence_proposals",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "evidence_proposals" in tables:
        indexes = [ix["name"] for ix in inspector.get_indexes("evidence_proposals")]
        for ix_name in (
            "ix_evidence_proposals_created_at",
            "ix_evidence_proposals_recommendation",
            "ix_evidence_proposals_evidence_status",
            "ix_evidence_proposals_ticker_symbol",
            "ix_evidence_proposals_experiment_id",
        ):
            if ix_name in indexes:
                op.drop_index(op.f(ix_name), table_name="evidence_proposals")
        op.drop_table("evidence_proposals")
