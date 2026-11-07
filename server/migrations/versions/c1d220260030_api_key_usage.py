"""api key usage

API-052（V180，152 号 spec）：API Key 每日用量 + 每把 Key 的每日配额。

Revision ID: c1d220260030
Revises: c1d220260029
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260030'
down_revision: Union[str, Sequence[str], None] = 'c1d220260029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.add_column(sa.Column('daily_quota', sa.Integer(), nullable=False, server_default='0'))
    op.create_table(
        'api_key_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('rejected', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_id', 'day'),
    )
    with op.batch_alter_table('api_key_usage') as batch:
        batch.create_index(batch.f('ix_api_key_usage_key_id'), ['key_id'], unique=False)


def downgrade() -> None:
    op.drop_table('api_key_usage')
    with op.batch_alter_table('api_keys') as batch:
        batch.drop_column('daily_quota')
