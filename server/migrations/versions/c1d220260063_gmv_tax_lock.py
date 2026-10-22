"""gmv_tax_lock

FIN-067（V285，258 号 spec）：成交额与代扣税表的锁账快照。

Revision ID: c1d220260063
Revises: c1d220260062
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260063'
down_revision: Union[str, Sequence[str], None] = 'c1d220260062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('finance_period_locks') as batch:
        batch.add_column(sa.Column('gmv_tax', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('finance_period_locks') as batch:
        batch.drop_column('gmv_tax')
