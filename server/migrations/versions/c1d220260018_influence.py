"""influence ledger, vouches and snapshots

INF-100~109（V152，127 号 spec）：影响力账本（只增不改）、质押担保、每日快照（Merkle 根锚定进存证链）。

Revision ID: c1d220260018
Revises: c1d220260017
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260018'
down_revision: Union[str, Sequence[str], None] = 'c1d220260017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'influence_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('points', sa.Float(), nullable=False),
        sa.Column('ref_type', sa.String(length=20), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'kind', 'ref_type', 'ref_id', name='uq_influence_event_once'),
    )
    op.create_index('ix_influence_events_user_id', 'influence_events', ['user_id'])
    op.create_index('ix_influence_events_category', 'influence_events', ['category'])
    op.create_index('ix_influence_events_created_at', 'influence_events', ['created_at'])
    op.create_table(
        'influence_vouches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('voucher_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('stake', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('dispute_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_influence_vouches_voucher_id', 'influence_vouches', ['voucher_id'])
    op.create_index('ix_influence_vouches_subject_id', 'influence_vouches', ['subject_id'])
    op.create_index('ix_influence_vouches_task_id', 'influence_vouches', ['task_id'])
    op.create_index('ix_influence_vouches_status', 'influence_vouches', ['status'])
    op.create_table(
        'influence_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('taken_at', sa.DateTime(), nullable=False),
        sa.Column('merkle_root', sa.String(length=64), nullable=False),
        sa.Column('leaves', sa.Integer(), nullable=False),
        sa.Column('anchor_seq', sa.Integer(), nullable=True),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_influence_snapshots_taken_at', 'influence_snapshots', ['taken_at'])


def downgrade() -> None:
    op.drop_index('ix_influence_snapshots_taken_at', table_name='influence_snapshots')
    op.drop_table('influence_snapshots')
    for ix in ('ix_influence_vouches_status', 'ix_influence_vouches_task_id', 'ix_influence_vouches_subject_id',
               'ix_influence_vouches_voucher_id'):
        op.drop_index(ix, table_name='influence_vouches')
    op.drop_table('influence_vouches')
    for ix in ('ix_influence_events_created_at', 'ix_influence_events_category', 'ix_influence_events_user_id'):
        op.drop_index(ix, table_name='influence_events')
    op.drop_table('influence_events')
