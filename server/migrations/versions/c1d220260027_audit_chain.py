"""audit chain

ADMIN-062（V177，149 号 spec）：审计日志哈希链（每条的上一条哈希与本条哈希）+ 链头。

Revision ID: c1d220260027
Revises: c1d220260026
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260027'
down_revision: Union[str, Sequence[str], None] = 'c1d220260026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('admin_audits') as batch:
        batch.add_column(sa.Column('prev_hash', sa.String(length=64), nullable=False, server_default=''))
        batch.add_column(sa.Column('hash', sa.String(length=64), nullable=False, server_default=''))
        batch.create_index(batch.f('ix_admin_audits_hash'), ['hash'], unique=False)
    op.create_table(
        'audit_chain_head',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_audit_id', sa.Integer(), nullable=False),
        sa.Column('last_hash', sa.String(length=64), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('audit_chain_head')
    with op.batch_alter_table('admin_audits') as batch:
        batch.drop_index(batch.f('ix_admin_audits_hash'))
        batch.drop_column('hash')
        batch.drop_column('prev_hash')
