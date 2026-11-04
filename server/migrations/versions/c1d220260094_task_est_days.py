"""tasks.est_days

AI-DEC-021c（V411，384 号 spec）：步骤的工期估计（天），驾驶舱按依赖排出时间线。

Revision ID: c1d220260094
Revises: c1d220260093
Create Date: 2026-11-04 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260094'
down_revision: Union[str, Sequence[str], None] = 'c1d220260093'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('est_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('est_days')
