"""progress_logs.days_left

AI-DEC-021d（V413，386 号 spec）：接单人更新进度时报的「还要几天」，驾驶舱时间线按它重排。

Revision ID: c1d220260095
Revises: c1d220260094
Create Date: 2026-11-04 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260095'
down_revision: Union[str, Sequence[str], None] = 'c1d220260094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.add_column(sa.Column('days_left', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.drop_column('days_left')
