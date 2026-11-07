"""change_order_shift

SCN-139（V235，207 号 spec）：多天名额改时段时给已签的名额发变更单，对方接受后名额的时段跟着改。
None = 这张变更单不改时段，"" = 改成不限时段。

Revision ID: c1d220260044
Revises: c1d220260043
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260044'
down_revision: Union[str, Sequence[str], None] = 'c1d220260043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('change_orders') as batch:
        batch.add_column(sa.Column('new_shift_start', sa.String(length=5), nullable=True))
        batch.add_column(sa.Column('new_shift_end', sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('change_orders') as batch:
        batch.drop_column('new_shift_end')
        batch.drop_column('new_shift_start')
