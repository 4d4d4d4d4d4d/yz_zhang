"""scenario_packs.expiry_reminded_at

SCN-163（V319，292 号 spec）：知识快到期时提醒写包的运营，记上次提醒的时间。

Revision ID: c1d220260073
Revises: c1d220260072
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260073'
down_revision: Union[str, Sequence[str], None] = 'c1d220260072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scenario_packs', sa.Column('expiry_reminded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('scenario_packs', 'expiry_reminded_at')
