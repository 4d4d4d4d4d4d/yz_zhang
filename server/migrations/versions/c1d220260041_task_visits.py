"""task_visits

SCN-120（V203，176 号 spec）：一单多次上门——要上门几次、每次要做的事；上门回报做了哪几项。

Revision ID: c1d220260041
Revises: c1d220260040
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260041'
down_revision: Union[str, Sequence[str], None] = 'c1d220260040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('visits_planned', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('visit_checklist', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('progress_logs') as batch:
        batch.add_column(sa.Column('checked', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('progress_logs') as batch:
        batch.drop_column('checked')
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('visit_checklist')
        batch.drop_column('visits_planned')
