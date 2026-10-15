"""announcement targeting

NTF-066（V185，159 号 spec）：公告按城市与人群定向。

Revision ID: c1d220260032
Revises: c1d220260031
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260032'
down_revision: Union[str, Sequence[str], None] = 'c1d220260031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.add_column(sa.Column('city', sa.String(length=50), nullable=False, server_default=''))
        batch.add_column(sa.Column('audience', sa.String(length=12), nullable=False, server_default='all'))


def downgrade() -> None:
    with op.batch_alter_table('announcements') as batch:
        batch.drop_column('audience')
        batch.drop_column('city')
