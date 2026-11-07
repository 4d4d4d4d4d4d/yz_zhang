"""team_spend_return_asked

TEAM-071（V257，230 号 spec）：所有者 / 管理员上一次提醒发起人退回拨款的时间。

Revision ID: c1d220260051
Revises: c1d220260050
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260051'
down_revision: Union[str, Sequence[str], None] = 'c1d220260050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.add_column(sa.Column('return_asked_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.drop_column('return_asked_at')
