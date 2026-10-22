"""method_version

AGT-097（V266，239 号 spec）：方法按版本分开统计效果。

Revision ID: c1d220260057
Revises: c1d220260056
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260057'
down_revision: Union[str, Sequence[str], None] = 'c1d220260056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('nb_methods') as batch:
        batch.add_column(sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    with op.batch_alter_table('missions') as batch:
        batch.add_column(sa.Column('method_version', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('missions') as batch:
        batch.drop_column('method_version')
    with op.batch_alter_table('nb_methods') as batch:
        batch.drop_column('version')
