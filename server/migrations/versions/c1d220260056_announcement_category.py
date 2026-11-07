"""announcement_category

NTF-068（V265，238 号 spec）：公告按类目定向。

Revision ID: c1d220260056
Revises: c1d220260055
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260056'
down_revision: Union[str, Sequence[str], None] = 'c1d220260055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.add_column(sa.Column('category', sa.String(length=50), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.drop_column('category')
