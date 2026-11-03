"""recipient_links

SCN-122（V383，356 号 spec）：替别人发单时给服务对象的免登录只读进度链接。

Revision ID: c1d220260090
Revises: c1d220260089
Create Date: 2026-11-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260090'
down_revision: Union[str, Sequence[str], None] = 'c1d220260089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recipient_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=False),
        sa.Column('last_viewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_recipient_links_task_id'), 'recipient_links', ['task_id'], unique=False)
    op.create_index(op.f('ix_recipient_links_created_by'), 'recipient_links', ['created_by'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_recipient_links_created_by'), table_name='recipient_links')
    op.drop_index(op.f('ix_recipient_links_task_id'), table_name='recipient_links')
    op.drop_table('recipient_links')
