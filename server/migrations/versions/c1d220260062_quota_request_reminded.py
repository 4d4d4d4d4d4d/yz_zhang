"""quota_request_reminded

API-058（V274，247 号 spec）：提额申请提醒运营。

Revision ID: c1d220260062
Revises: c1d220260061
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260062'
down_revision: Union[str, Sequence[str], None] = 'c1d220260061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('api_quota_requests') as batch:
        batch.add_column(sa.Column('reminded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('api_quota_requests') as batch:
        batch.drop_column('reminded_at')
