"""visit_confirmation

SCN-192（V344，317 号 spec）：发单人对一次上门回报的确认 / 异议。

Revision ID: c1d220260080
Revises: c1d220260079
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260080'
down_revision: Union[str, Sequence[str], None] = 'c1d220260079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.add_column(sa.Column('confirmed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('objection', sa.String(length=300), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.drop_column('objection')
        batch.drop_column('confirmed_at')
