"""api_account_quotas

API-056（V262，235 号 spec）：给某个接入方单独调整的开放 API 账号每日总配额。

Revision ID: c1d220260053
Revises: c1d220260052
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260053'
down_revision: Union[str, Sequence[str], None] = 'c1d220260052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_account_quotas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('daily_quota', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('set_by', sa.Integer(), nullable=False),
        sa.Column('set_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_account_quotas_user_id', 'api_account_quotas', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_api_account_quotas_user_id', table_name='api_account_quotas')
    op.drop_table('api_account_quotas')
