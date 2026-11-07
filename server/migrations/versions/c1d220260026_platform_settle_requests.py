"""platform settle requests

SEC-061c / PAY-042b（V176，148 号 spec）：大额平台结算要两位不同的财务先后确认。

Revision ID: c1d220260026
Revises: c1d220260025
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260026'
down_revision: Union[str, Sequence[str], None] = 'c1d220260025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_settle_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('memo', sa.String(length=200), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decision_reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_platform_settle_requests_requested_by'), 'platform_settle_requests', ['requested_by'], unique=False)
    op.create_index(op.f('ix_platform_settle_requests_status'), 'platform_settle_requests', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_platform_settle_requests_status'), table_name='platform_settle_requests')
    op.drop_index(op.f('ix_platform_settle_requests_requested_by'), table_name='platform_settle_requests')
    op.drop_table('platform_settle_requests')
