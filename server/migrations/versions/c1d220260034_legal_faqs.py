"""legal_faqs

LAW-060 / SCN-114（V192，163 号 spec）：法律常识库的运营草稿流（草稿 → 审核 → 上线 → 下线）。

Revision ID: c1d220260034
Revises: c1d220260033
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260034'
down_revision: Union[str, Sequence[str], None] = 'c1d220260033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legal_faqs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=20), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('origin', sa.String(length=60), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('retired_reason', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('legal_faqs') as batch:
        batch.create_index(batch.f('ix_legal_faqs_topic'), ['topic'], unique=False)
        batch.create_index(batch.f('ix_legal_faqs_status'), ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('legal_faqs')
