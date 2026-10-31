"""category_fresh_days

KB-062b（V354，327 号 spec）：经验时效窗口按类目可配；空 = 平台默认 365 天。

Revision ID: c1d220260083
Revises: c1d220260082
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260083'
down_revision: Union[str, Sequence[str], None] = 'c1d220260082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('categories') as batch:
        batch.add_column(sa.Column('experience_fresh_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('categories') as batch:
        batch.drop_column('experience_fresh_days')
