"""bonus_tiers

OUT-050（V470，443 号 spec）浮动对价分档：任务与合同各存一份（合同里是签约那一刻的快照）。

Revision ID: c1d220260102
Revises: c1d220260101
Create Date: 2026-11-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260102'
down_revision: Union[str, Sequence[str], None] = 'c1d220260101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as b:
        b.add_column(sa.Column('bonus_tiers', sa.JSON(), nullable=True))
    with op.batch_alter_table('contracts') as b:
        b.add_column(sa.Column('bonus_tiers', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('contracts') as b:
        b.drop_column('bonus_tiers')
    with op.batch_alter_table('tasks') as b:
        b.drop_column('bonus_tiers')
