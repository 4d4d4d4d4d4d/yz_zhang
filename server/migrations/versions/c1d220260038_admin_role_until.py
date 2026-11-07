"""admin_role_until

SEC-061e（V198，171 号 spec）：管理员临时角色的到期时间。

Revision ID: c1d220260038
Revises: c1d220260037
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260038'
down_revision: Union[str, Sequence[str], None] = 'c1d220260037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('admin_role_until', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('admin_role_until')
