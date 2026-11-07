"""admin roles

SEC-061b（V169，141 号 spec）：管理员分级。空列表 = 未分级，按超级管理员对待（兼容此前的全部管理员）。

Revision ID: c1d220260023
Revises: c1d220260022
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260023'
down_revision: Union[str, Sequence[str], None] = 'c1d220260022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('admin_roles', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('admin_roles')
