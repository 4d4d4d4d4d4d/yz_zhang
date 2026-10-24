"""announcement_categories

NTF-070（V273，246 号 spec）：公告按多个类目定向。

Revision ID: c1d220260061
Revises: c1d220260060
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260061'
down_revision: Union[str, Sequence[str], None] = 'c1d220260060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.add_column(sa.Column('categories', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.drop_column('categories')
