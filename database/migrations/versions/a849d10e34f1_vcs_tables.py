"""Add VCS tables and LISTEN/NOTIFY trigger

Revision ID: a849d10e34f1
Revises: c729b59f57ab
Create Date: 2026-07-31 19:12:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a849d10e34f1'
down_revision: Union[str, None] = 'c729b59f57ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create vcs_blobs
    op.create_table(
        'vcs_blobs',
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('hash')
    )

    # 2. Create vcs_commits
    op.create_table(
        'vcs_commits',
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.Column('blob_hash', sa.String(length=64), nullable=False),
        sa.Column('parent_hash', sa.String(length=64), nullable=True),
        sa.Column('author', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['blob_hash'], ['vcs_blobs.hash'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['parent_hash'], ['vcs_commits.hash'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('hash')
    )
    op.create_index(op.f('ix_vcs_commits_blob_hash'), 'vcs_commits', ['blob_hash'], unique=False)
    op.create_index(op.f('ix_vcs_commits_parent_hash'), 'vcs_commits', ['parent_hash'], unique=False)

    # 3. Create vcs_refs
    op.create_table(
        'vcs_refs',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('commit_hash', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['commit_hash'], ['vcs_commits.hash'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('name')
    )

    # 4. Trigger function for LISTEN/NOTIFY on vcs_refs updates
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_vcs_ref_update() RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify(
                'vcs_ref_update',
                json_build_object(
                    'ref', NEW.name,
                    'commit', NEW.commit_hash
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_vcs_ref_update
        AFTER INSERT OR UPDATE ON vcs_refs
        FOR EACH ROW EXECUTE FUNCTION notify_vcs_ref_update();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_vcs_ref_update ON vcs_refs;")
    op.execute("DROP FUNCTION IF EXISTS notify_vcs_ref_update();")
    op.drop_table('vcs_refs')
    op.drop_index(op.f('ix_vcs_commits_parent_hash'), table_name='vcs_commits')
    op.drop_index(op.f('ix_vcs_commits_blob_hash'), table_name='vcs_commits')
    op.drop_table('vcs_commits')
    op.drop_table('vcs_blobs')
