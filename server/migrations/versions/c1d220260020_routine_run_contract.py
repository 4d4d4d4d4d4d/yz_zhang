"""routine run contract and run log

REL-101~106（V153，130 号 spec）：例行任务的运行合同（超时、重试、降级）与运行日志（排期、尝试次数、耗时、成本、错误类型）。
已有的行按原来的行为：不重试、不降级。

Revision ID: c1d220260020
Revises: c1d220260019
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260020'
down_revision: Union[str, Sequence[str], None] = 'c1d220260019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('wb_routines') as b:
        b.add_column(sa.Column('timeout_ms', sa.Integer(), nullable=False, server_default='10000'))
        b.add_column(sa.Column('max_retries', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('degrade', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('pending_slot_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('wb_routine_runs') as b:
        b.add_column(sa.Column('slot_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'))
        b.add_column(sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('cost_cents', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('error_kind', sa.String(length=40), nullable=False, server_default=''))
        b.add_column(sa.Column('degraded', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.create_index('ix_wb_routine_runs_slot_at', ['slot_at'])


def downgrade() -> None:
    with op.batch_alter_table('wb_routine_runs') as b:
        b.drop_index('ix_wb_routine_runs_slot_at')
        for c in ('degraded', 'error_kind', 'cost_cents', 'duration_ms', 'attempt', 'slot_at'):
            b.drop_column(c)
    with op.batch_alter_table('wb_routines') as b:
        for c in ('pending_slot_at', 'retry_count', 'degrade', 'max_retries', 'timeout_ms'):
            b.drop_column(c)
