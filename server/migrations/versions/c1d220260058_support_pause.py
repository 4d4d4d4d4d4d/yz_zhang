"""support_pause

ESCA-065（V267，240 号 spec）：客服暂停接单。

Revision ID: c1d220260058
Revises: c1d220260057
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260058'
down_revision: Union[str, Sequence[str], None] = 'c1d220260057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.add_column(sa.Column('paused_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.drop_column('paused_until')
