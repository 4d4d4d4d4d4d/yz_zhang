"""task_days

SCN-107（V194，167 号 spec）：一单多人、多天——任务记连续几天，名额记是哪一天。

Revision ID: c1d220260036
Revises: c1d220260035
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260036'
down_revision: Union[str, Sequence[str], None] = 'c1d220260035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('days', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('work_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('work_date')
        batch.drop_column('days')
