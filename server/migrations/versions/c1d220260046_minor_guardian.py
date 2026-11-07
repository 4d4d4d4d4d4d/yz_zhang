"""minor_guardian

SCN-144（V242，214 号 spec）：服务对象是未成年人的任务——是否涉及未成年人、监护人安排方式（在场 / 公开场所）、
监护人确认的时间。不存孩子的任何信息。

Revision ID: c1d220260046
Revises: c1d220260045
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260046'
down_revision: Union[str, Sequence[str], None] = 'c1d220260045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('minor_involved', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('guardian_mode', sa.String(length=20), nullable=False, server_default=''))
        batch.add_column(sa.Column('guardian_consent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('guardian_consent_at')
        batch.drop_column('guardian_mode')
        batch.drop_column('minor_involved')
