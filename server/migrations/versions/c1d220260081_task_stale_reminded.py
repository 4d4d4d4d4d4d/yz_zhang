"""task_stale_reminded

AI-DEC-023（V347，320 号 spec）：招募多天没人报名时上次提醒发单人的时间。

Revision ID: c1d220260081
Revises: c1d220260080
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260081'
down_revision: Union[str, Sequence[str], None] = 'c1d220260080'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('stale_reminded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('stale_reminded_at')
