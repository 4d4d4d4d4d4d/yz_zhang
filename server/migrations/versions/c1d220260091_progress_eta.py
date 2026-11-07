"""progress_logs.eta_at

SCN-122c（V392，364 号 spec）：接单人「出发了」时的预计到达时间。

Revision ID: c1d220260091
Revises: c1d220260090
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260091'
down_revision: Union[str, Sequence[str], None] = 'c1d220260090'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.add_column(sa.Column('eta_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.drop_column('eta_at')
