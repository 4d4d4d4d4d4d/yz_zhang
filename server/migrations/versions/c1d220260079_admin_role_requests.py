"""admin_role_requests

SEC-061i（V342，315 号 spec）：临时角色的申请与审批。

Revision ID: c1d220260079
Revises: c1d220260078
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260079'
down_revision: Union[str, Sequence[str], None] = 'c1d220260078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_role_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('hours', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_note', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_admin_role_requests_user_id'), 'admin_role_requests', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_admin_role_requests_user_id'), table_name='admin_role_requests')
    op.drop_table('admin_role_requests')
