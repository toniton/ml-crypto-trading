"""Add trades table or missing columns (metadata, slippage)

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-09-27 12:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'i1a2b3c4d5e6'
down_revision: Union[str, None] = 'h1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    json_type = sa.JSON().with_variant(JSONB, 'postgresql')

    if 'trades' not in tables:
        op.create_table(
            'trades',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('trade_id', sa.String(), nullable=True),
            sa.Column('ticker_symbol', sa.String(), nullable=True),
            sa.Column('entry_order_uuid', sa.String(), nullable=True),
            sa.Column('exit_order_uuid', sa.String(), nullable=True),
            sa.Column('entry_price', sa.String(), nullable=True),
            sa.Column('exit_price', sa.String(), nullable=True),
            sa.Column('quantity', sa.String(), nullable=True),
            sa.Column('gross_pnl', sa.String(), nullable=True),
            sa.Column('fees', sa.String(), nullable=True),
            sa.Column('slippage', sa.String(), nullable=True),
            sa.Column('net_pnl', sa.String(), nullable=True),
            sa.Column('return_pct', sa.String(), nullable=True),
            sa.Column('duration_seconds', sa.Float(), nullable=True),
            sa.Column('entry_timestamp', sa.TIMESTAMP(), nullable=True),
            sa.Column('exit_timestamp', sa.TIMESTAMP(), nullable=True),
            sa.Column('metadata', json_type, server_default='{}', nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_trades_trade_id'), 'trades', ['trade_id'], unique=True)
        op.create_index(op.f('ix_trades_ticker_symbol'), 'trades', ['ticker_symbol'], unique=False)
        op.create_index(op.f('ix_trades_entry_order_uuid'), 'trades', ['entry_order_uuid'], unique=False)
        op.create_index(op.f('ix_trades_exit_order_uuid'), 'trades', ['exit_order_uuid'], unique=False)
    else:
        columns = [c['name'] for c in inspector.get_columns('trades')]
        if 'metadata' not in columns:
            op.add_column('trades', sa.Column('metadata', json_type, server_default='{}', nullable=True))
        if 'slippage' not in columns:
            op.add_column('trades', sa.Column('slippage', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'trades' in tables:
        columns = [c['name'] for c in inspector.get_columns('trades')]
        if 'metadata' in columns:
            op.drop_column('trades', 'metadata')
        if 'slippage' in columns:
            op.drop_column('trades', 'slippage')
