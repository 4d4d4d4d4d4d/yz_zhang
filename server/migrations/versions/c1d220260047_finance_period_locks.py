"""finance_period_locks

FIN-063（V250，223 号 spec）：已锁账月份的报表快照。锁过的月份报表只读快照，
补记记到第一个未锁月份。

Revision ID: c1d220260047
Revises: c1d220260046
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260047'
down_revision: Union[str, Sequence[str], None] = 'c1d220260046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'finance_period_locks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('in_month_cents', sa.Integer(), nullable=False),
        sa.Column('in_month_count', sa.Integer(), nullable=False),
        sa.Column('cumulative', sa.JSON(), nullable=False),
        sa.Column('locked_by', sa.Integer(), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period'),
    )


def downgrade() -> None:
    op.drop_table('finance_period_locks')
