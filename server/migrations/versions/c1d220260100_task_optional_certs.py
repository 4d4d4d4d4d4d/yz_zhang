"""categories.optional_certs / tasks.task_certs

SCN-294b（V434，407 号 spec）：类目列出发单人可以按这一单加选的资质；任务记下发单人加选了哪几张。

Revision ID: c1d220260100
Revises: c1d220260099
Create Date: 2026-11-05 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260100'
down_revision: Union[str, Sequence[str], None] = 'c1d220260099'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('categories') as batch:
        batch.add_column(sa.Column('optional_certs', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('task_certs', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('task_certs')
    with op.batch_alter_table('categories') as batch:
        batch.drop_column('optional_certs')
