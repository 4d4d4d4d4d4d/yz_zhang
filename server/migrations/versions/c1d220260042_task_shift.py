"""task_shift

SCN-117（V205，178 号 spec）：多天名额的每天时段（北京时间 HH:MM）。

Revision ID: c1d220260042
Revises: c1d220260041
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260042'
down_revision: Union[str, Sequence[str], None] = 'c1d220260041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('shift_start', sa.String(length=5), nullable=False, server_default=''))
        batch.add_column(sa.Column('shift_end', sa.String(length=5), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('shift_end')
        batch.drop_column('shift_start')
