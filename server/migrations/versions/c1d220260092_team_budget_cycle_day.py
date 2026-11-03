"""teams.budget_cycle_day

TEAM-056（V397，370 号 spec）：团队预算池按每月几号重置（1~28，默认 1 = 原来的自然月）。

Revision ID: c1d220260092
Revises: c1d220260091
Create Date: 2026-11-03 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260092'
down_revision: Union[str, Sequence[str], None] = 'c1d220260091'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('teams') as batch:
        batch.add_column(sa.Column('budget_cycle_day', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('teams') as batch:
        batch.drop_column('budget_cycle_day')
