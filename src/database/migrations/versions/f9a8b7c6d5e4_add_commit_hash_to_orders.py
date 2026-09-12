"""Add commit_hash to orders

Revision ID: f9a8b7c6d5e4
Revises: e8b1c2d3e4f5
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9a8b7c6d5e4'
down_revision: Union[str, None] = 'e8b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('commit_hash', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'commit_hash')
