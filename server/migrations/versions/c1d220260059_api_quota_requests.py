"""api_quota_requests

API-057（V268，241 号 spec）：接入方自己申请提额，运营在后台批。

Revision ID: c1d220260059
Revises: c1d220260058
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260059'
down_revision: Union[str, Sequence[str], None] = 'c1d220260058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_quota_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('daily_quota', sa.Integer(), nullable=False),
        sa.Column('days', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_note', sa.String(length=200), nullable=False),
        sa.Column('granted_quota', sa.Integer(), nullable=True),
        sa.Column('granted_days', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_quota_requests_user_id'), 'api_quota_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_api_quota_requests_status'), 'api_quota_requests', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_quota_requests_status'), table_name='api_quota_requests')
    op.drop_index(op.f('ix_api_quota_requests_user_id'), table_name='api_quota_requests')
    op.drop_table('api_quota_requests')
