"""support_auto_assign

ESCA-064（V264，237 号 spec）：客服打开「新工单自动分给我」。

Revision ID: c1d220260055
Revises: c1d220260054
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260055'
down_revision: Union[str, Sequence[str], None] = 'c1d220260054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.add_column(sa.Column('auto_assign', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.drop_column('auto_assign')
