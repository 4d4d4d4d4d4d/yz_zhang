"""errand_reviews

SCN-219（V363，336 号 spec）：被发单拦截挡下时申请人工复核。

Revision ID: c1d220260087
Revises: c1d220260086
Create Date: 2026-10-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260087'
down_revision: Union[str, Sequence[str], None] = 'c1d220260086'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'errand_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('explanation', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decision_note', sa.String(length=300), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_errand_reviews_user_id'), 'errand_reviews', ['user_id'], unique=False)
    op.create_index(op.f('ix_errand_reviews_fingerprint'), 'errand_reviews', ['fingerprint'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_errand_reviews_fingerprint'), table_name='errand_reviews')
    op.drop_index(op.f('ix_errand_reviews_user_id'), table_name='errand_reviews')
    op.drop_table('errand_reviews')
