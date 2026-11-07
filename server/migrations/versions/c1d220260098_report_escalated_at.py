"""reports.escalated_at

RISK-018（V429，402 号 spec）：举报超过处理时限、已经叫过合规的时间，每条只叫一次。

Revision ID: c1d220260098
Revises: c1d220260097
Create Date: 2026-11-04 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260098'
down_revision: Union[str, Sequence[str], None] = 'c1d220260097'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.add_column(sa.Column('escalated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.drop_column('escalated_at')
