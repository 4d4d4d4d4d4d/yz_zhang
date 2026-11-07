"""team_approval_rotation

TEAM-064（V263，236 号 spec）：团队审批通知方式（发给所有管理员 / 轮流指派一人）与每笔支出轮到谁。

Revision ID: c1d220260054
Revises: c1d220260053
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260054'
down_revision: Union[str, Sequence[str], None] = 'c1d220260053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('teams') as batch:
        batch.add_column(sa.Column('approval_mode', sa.String(length=10), nullable=False, server_default='all'))
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.add_column(sa.Column('assignee_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.drop_column('assignee_id')
    with op.batch_alter_table('teams') as batch:
        batch.drop_column('approval_mode')
