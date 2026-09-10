"""add backtest tables

Revision ID: e8b1c2d3e4f5
Revises: e7a9b1c3d5f0
Create Date: 2026-09-09 23:59:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'e8b1c2d3e4f5'
down_revision: Union[str, None] = 'e7a9b1c3d5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'backtest_sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('ticker_symbol', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='RUNNING'),
        sa.Column('config', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_backtest_sessions_ticker_symbol'), 'backtest_sessions', ['ticker_symbol'])
    op.create_index(op.f('ix_backtest_sessions_created_at'), 'backtest_sessions', ['created_at'])

    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('ticker_symbol', sa.String(length=32), nullable=False),
        sa.Column('data', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['backtest_sessions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('session_id'),
    )
    op.create_index(op.f('ix_backtest_results_session_id'), 'backtest_results', ['session_id'], unique=True)
    op.create_index(op.f('ix_backtest_results_ticker_symbol'), 'backtest_results', ['ticker_symbol'])


def downgrade() -> None:
    op.drop_index(op.f('ix_backtest_results_ticker_symbol'), table_name='backtest_results')
    op.drop_index(op.f('ix_backtest_results_session_id'), table_name='backtest_results')
    op.drop_table('backtest_results')
    op.drop_index(op.f('ix_backtest_sessions_created_at'), table_name='backtest_sessions')
    op.drop_index(op.f('ix_backtest_sessions_ticker_symbol'), table_name='backtest_sessions')
    op.drop_table('backtest_sessions')
