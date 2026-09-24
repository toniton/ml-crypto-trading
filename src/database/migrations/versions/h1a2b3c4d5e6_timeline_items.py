"""Add timeline items table

Revision ID: h1a2b3c4d5e6
Revises: g1a2b3c4d5e6
Create Date: 2026-09-24 22:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'h1a2b3c4d5e6'
down_revision: Union[str, None] = 'g1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, 'postgresql')

    op.create_table(
        'timeline_items',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False, server_default='INFO'),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('causation_id', sa.String(length=64), nullable=True),
        sa.Column('actor_type', sa.String(length=32), nullable=True),
        sa.Column('actor_id', sa.String(length=64), nullable=True),
        sa.Column('primary_entity_type', sa.String(length=32), nullable=True),
        sa.Column('primary_entity_id', sa.String(length=64), nullable=True),
        sa.Column('entities', json_type, nullable=True),
        sa.Column('artifacts', json_type, nullable=True),
        sa.Column('metadata', json_type, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_timeline_items_timestamp'), 'timeline_items', ['timestamp'], unique=False)
    op.create_index(op.f('ix_timeline_items_category'), 'timeline_items', ['category'], unique=False)
    op.create_index(op.f('ix_timeline_items_severity'), 'timeline_items', ['severity'], unique=False)
    op.create_index(op.f('ix_timeline_items_correlation_id'), 'timeline_items', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_timeline_items_actor_type'), 'timeline_items', ['actor_type'], unique=False)
    op.create_index(op.f('ix_timeline_items_primary_entity_type'), 'timeline_items', ['primary_entity_type'], unique=False)
    op.create_index(op.f('ix_timeline_items_primary_entity_id'), 'timeline_items', ['primary_entity_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_timeline_items_primary_entity_id'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_primary_entity_type'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_actor_type'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_correlation_id'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_severity'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_category'), table_name='timeline_items')
    op.drop_index(op.f('ix_timeline_items_timestamp'), table_name='timeline_items')
    op.drop_table('timeline_items')
