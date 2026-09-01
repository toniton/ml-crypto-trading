"""add metric tables

Revision ID: e7a9b1c3d5f0
Revises: 61312552e200
Create Date: 2026-08-31 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'e7a9b1c3d5f0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'metric_definitions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('metric_type', sa.String(length=16), nullable=False),
        sa.Column('unit', sa.String(), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('aggregation', sa.String(length=16), nullable=True),
        sa.Column('retention_seconds', sa.BigInteger(), nullable=False, server_default='2592000'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_metric_definitions_name'), 'metric_definitions', ['name'], unique=True)

    op.create_table(
        'metric_samples',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('metric_id', sa.String(length=32), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('labels', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['metric_id'], ['metric_definitions.id']),
    )
    op.create_index(op.f('ix_metric_samples_metric_id'), 'metric_samples', ['metric_id'])
    op.create_index(op.f('ix_metric_samples_timestamp'), 'metric_samples', ['timestamp'])


def downgrade() -> None:
    op.drop_index(op.f('ix_metric_samples_timestamp'), table_name='metric_samples')
    op.drop_index(op.f('ix_metric_samples_metric_id'), table_name='metric_samples')
    op.drop_table('metric_samples')
    op.drop_index(op.f('ix_metric_definitions_name'), table_name='metric_definitions')
    op.drop_table('metric_definitions')
