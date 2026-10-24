"""notification_read_at

NTF-072（V288，261 号 spec）：通知第一次点开的时间。

Revision ID: c1d220260065
Revises: c1d220260064
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260065'
down_revision: Union[str, Sequence[str], None] = 'c1d220260064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.add_column(sa.Column('read_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_column('read_at')
