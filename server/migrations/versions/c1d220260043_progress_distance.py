"""progress_distance

SCN-124（V222，195 号 spec）：上门回报与打卡记下离任务地点多远（米）。坐标按 GEO 规则在任务结束后清掉，
距离是一个数字、不是位置，留着当履约证据。

Revision ID: c1d220260043
Revises: c1d220260042
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260043'
down_revision: Union[str, Sequence[str], None] = 'c1d220260042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.add_column(sa.Column('distance_m', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.drop_column('distance_m')
