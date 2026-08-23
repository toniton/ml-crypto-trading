"""Add payload and message_id to conversation_messages

Revision ID: f1a2b3c4d5e6
Revises: e5f2a1b3c4d6
Create Date: 2026-08-23 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f2a1b3c4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_messages', sa.Column('message_id', sa.String(length=32), nullable=True))
    op.add_column(
        'conversation_messages',
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversation_messages', 'payload')
    op.drop_column('conversation_messages', 'message_id')
