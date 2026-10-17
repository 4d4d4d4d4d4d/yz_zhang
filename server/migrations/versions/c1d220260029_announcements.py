"""announcements

NTF-064（V179，151 号 spec）：全站公告记录（预览、定时、撤回）+ 通知记下来自哪条公告。

Revision ID: c1d220260029
Revises: c1d220260028
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260029'
down_revision: Union[str, Sequence[str], None] = 'c1d220260028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'announcements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.String(length=2000), nullable=False),
        sa.Column('verified_only', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered', sa.Integer(), nullable=False),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('close_reason', sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('announcements') as batch:
        batch.create_index(batch.f('ix_announcements_status'), ['status'], unique=False)
        batch.create_index(batch.f('ix_announcements_created_by'), ['created_by'], unique=False)
    with op.batch_alter_table('notifications') as batch:
        batch.add_column(sa.Column('announcement_id', sa.Integer(), nullable=True))
        batch.create_index(batch.f('ix_notifications_announcement_id'), ['announcement_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_index(batch.f('ix_notifications_announcement_id'))
        batch.drop_column('announcement_id')
    op.drop_table('announcements')
