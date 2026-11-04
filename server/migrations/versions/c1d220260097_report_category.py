"""reports.category / reports.resolved_at

RISK-010/012（V426，399 号 spec）：举报带类型（老数据记为 other），处理时记下时间，举报人能看到处理结果。

Revision ID: c1d220260097
Revises: c1d220260096
Create Date: 2026-11-04 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260097'
down_revision: Union[str, Sequence[str], None] = 'c1d220260096'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.add_column(sa.Column('category', sa.String(length=20), nullable=False, server_default='other'))
        batch.add_column(sa.Column('resolved_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.drop_column('resolved_at')
        batch.drop_column('category')
