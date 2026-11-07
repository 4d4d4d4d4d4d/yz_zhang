"""mission_method

AGT-094（V187，164 号 spec）：编排可以按本人的「我的方法」拆第一轮。

Revision ID: c1d220260035
Revises: c1d220260034
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260035'
down_revision: Union[str, Sequence[str], None] = 'c1d220260034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('missions') as batch:
        batch.add_column(sa.Column('method_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('missions') as batch:
        batch.drop_column('method_id')
