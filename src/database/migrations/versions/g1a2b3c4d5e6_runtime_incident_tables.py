"""add runtime incident and error event tables

Revision ID: g1a2b3c4d5e6
Revises: f9a8b7c6d5e4
Create Date: 2026-09-20 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, None] = 'f9a8b7c6d5e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, 'postgresql')

    op.create_table(
        'runtime_incidents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('component', sa.String(length=128), nullable=False),
        sa.Column('operation', sa.String(length=128), nullable=True),
        sa.Column('asset', sa.String(length=64), nullable=True),
        sa.Column('exchange', sa.String(length=64), nullable=True),
        sa.Column('commit_hash', sa.String(length=64), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('diagnosis', json_type, nullable=True),
        sa.Column('suggestion', json_type, nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_runtime_incidents_fingerprint'), 'runtime_incidents', ['fingerprint'], unique=False)
    op.create_index(op.f('ix_runtime_incidents_status'), 'runtime_incidents', ['status'], unique=False)
    op.create_index(op.f('ix_runtime_incidents_category'), 'runtime_incidents', ['category'], unique=False)
    op.create_index(op.f('ix_runtime_incidents_severity'), 'runtime_incidents', ['severity'], unique=False)
    op.create_index(op.f('ix_runtime_incidents_asset'), 'runtime_incidents', ['asset'], unique=False)
    op.create_index(op.f('ix_runtime_incidents_exchange'), 'runtime_incidents', ['exchange'], unique=False)

    op.create_table(
        'runtime_error_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('incident_id', sa.String(length=36), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('component', sa.String(length=128), nullable=False),
        sa.Column('error_type', sa.String(length=128), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('operation', sa.String(length=128), nullable=True),
        sa.Column('asset', sa.String(length=64), nullable=True),
        sa.Column('order_id', sa.String(length=64), nullable=True),
        sa.Column('exchange', sa.String(length=64), nullable=True),
        sa.Column('exchange_code', sa.Integer(), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('commit_hash', sa.String(length=64), nullable=True),
        sa.Column('metadata_payload', json_type, nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['incident_id'], ['runtime_incidents.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_runtime_error_events_incident_id'), 'runtime_error_events', ['incident_id'], unique=False)
    op.create_index(op.f('ix_runtime_error_events_timestamp'), 'runtime_error_events', ['timestamp'], unique=False)
    op.create_index(op.f('ix_runtime_error_events_fingerprint'), 'runtime_error_events', ['fingerprint'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_runtime_error_events_fingerprint'), table_name='runtime_error_events')
    op.drop_index(op.f('ix_runtime_error_events_timestamp'), table_name='runtime_error_events')
    op.drop_index(op.f('ix_runtime_error_events_incident_id'), table_name='runtime_error_events')
    op.drop_table('runtime_error_events')
    op.drop_index(op.f('ix_runtime_incidents_exchange'), table_name='runtime_incidents')
    op.drop_index(op.f('ix_runtime_incidents_asset'), table_name='runtime_incidents')
    op.drop_index(op.f('ix_runtime_incidents_severity'), table_name='runtime_incidents')
    op.drop_index(op.f('ix_runtime_incidents_category'), table_name='runtime_incidents')
    op.drop_index(op.f('ix_runtime_incidents_status'), table_name='runtime_incidents')
    op.drop_index(op.f('ix_runtime_incidents_fingerprint'), table_name='runtime_incidents')
    op.drop_table('runtime_incidents')
