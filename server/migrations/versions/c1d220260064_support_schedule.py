"""support_schedule

ESCA-068（V287，260 号 spec）：客服排班。

Revision ID: c1d220260064
Revises: c1d220260063
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260064'
down_revision: Union[str, Sequence[str], None] = 'c1d220260063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.add_column(sa.Column('schedule', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.drop_column('schedule')
