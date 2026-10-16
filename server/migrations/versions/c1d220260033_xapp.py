"""xapp

XAPP-001~010（V190，161 号 spec）：跨 App 助手的授权、执行与步骤。

Revision ID: c1d220260033
Revises: c1d220260032
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260033'
down_revision: Union[str, Sequence[str], None] = 'c1d220260032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'xapp_grants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_label', sa.String(length=60), nullable=False),
        sa.Column('apps', sa.JSON(), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=False),
        sa.Column('allow_cloud_vision', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('xapp_grants') as batch:
        batch.create_index(batch.f('ix_xapp_grants_user_id'), ['user_id'], unique=False)
    op.create_table(
        'xapp_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('grant_id', sa.Integer(), nullable=False),
        sa.Column('goal', sa.String(length=200), nullable=False),
        sa.Column('executor', sa.String(length=16), nullable=False),
        sa.Column('confirm_mode', sa.String(length=12), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('stop_reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('xapp_runs') as batch:
        batch.create_index(batch.f('ix_xapp_runs_user_id'), ['user_id'], unique=False)
        batch.create_index(batch.f('ix_xapp_runs_grant_id'), ['grant_id'], unique=False)
        batch.create_index(batch.f('ix_xapp_runs_status'), ['status'], unique=False)
    op.create_table(
        'xapp_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('app', sa.String(length=120), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('intent', sa.String(length=200), nullable=False),
        sa.Column('channel', sa.String(length=10), nullable=False),
        sa.Column('vision_where', sa.String(length=8), nullable=False),
        sa.Column('red_line', sa.Boolean(), nullable=False),
        sa.Column('needs_confirm', sa.Boolean(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=14), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('result', sa.String(length=500), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('xapp_steps') as batch:
        batch.create_index(batch.f('ix_xapp_steps_run_id'), ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_table('xapp_steps')
    op.drop_table('xapp_runs')
    op.drop_table('xapp_grants')
