"""api key rate

API-050（V173，145 号 spec）：每把 API Key 自己的每分钟上限；0 = 平台默认。

Revision ID: c1d220260024
Revises: c1d220260023
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260024'
down_revision: Union[str, Sequence[str], None] = 'c1d220260023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.add_column(sa.Column('rate_per_minute', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.drop_column('rate_per_minute')
