"""team_spend_returned

TEAM-070（V253，226 号 spec）：团队拨款里发起人已经退回团队的钱。

Revision ID: c1d220260048
Revises: c1d220260047
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260048'
down_revision: Union[str, Sequence[str], None] = 'c1d220260047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.add_column(sa.Column('returned_cents', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('team_spend_requests') as batch:
        batch.drop_column('returned_cents')
