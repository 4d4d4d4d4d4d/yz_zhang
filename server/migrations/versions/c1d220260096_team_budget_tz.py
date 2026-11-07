"""teams.budget_tz

TEAM-056b（V419，392 号 spec）：团队账期按负责人选的时区 0 点起算；空 = UTC（与原来一样）。

Revision ID: c1d220260096
Revises: c1d220260095
Create Date: 2026-11-04 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260096'
down_revision: Union[str, Sequence[str], None] = 'c1d220260095'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('teams') as batch:
        batch.add_column(sa.Column('budget_tz', sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('teams') as batch:
        batch.drop_column('budget_tz')
