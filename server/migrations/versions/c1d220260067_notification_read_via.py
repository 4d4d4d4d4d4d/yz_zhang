"""notification_read_via

NTF-073（V295，268 号 spec）：通知第一次是从推送还是通知中心点开的。

Revision ID: c1d220260067
Revises: c1d220260066
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260067'
down_revision: Union[str, Sequence[str], None] = 'c1d220260066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.add_column(sa.Column('read_via', sa.String(length=8), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_column('read_via')
