"""change orders: deadline and scope

SC-007b（V144，119 号 spec）：变更单除了改价，还能改截止时间与范围（可以一起改）。
不改价的变更单 new_amount_cents 记原金额，原有改价语义不变。

Revision ID: c1d220260013
Revises: c1d220260012
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260013'
down_revision: Union[str, Sequence[str], None] = 'c1d220260012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('change_orders') as b:
        b.add_column(sa.Column('new_deadline', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('scope_change', sa.String(length=1000), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('change_orders') as b:
        b.drop_column('scope_change')
        b.drop_column('new_deadline')
