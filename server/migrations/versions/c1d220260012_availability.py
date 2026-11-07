"""availability: weekly slots, limited capacity, invitation response time

SPACE-023（V143，118 号 spec）：可用时段与「少量接单」进入撮合；邀约记下回复时刻，
用来算「通常多久回复邀约」（样本足够才显示）。原有的 available_times 文字描述与接单开关不动。

Revision ID: c1d220260012
Revises: c1d220260011
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260012'
down_revision: Union[str, Sequence[str], None] = 'c1d220260011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('weekly_slots', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('limited_capacity', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('invitations') as b:
        b.add_column(sa.Column('responded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('invitations') as b:
        b.drop_column('responded_at')
    with op.batch_alter_table('users') as b:
        b.drop_column('limited_capacity')
        b.drop_column('weekly_slots')
