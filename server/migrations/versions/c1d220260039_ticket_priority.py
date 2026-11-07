"""ticket_priority

ESCA-052（V199，172 号 spec）：工单类别与优先级。

Revision ID: c1d220260039
Revises: c1d220260038
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260039'
down_revision: Union[str, Sequence[str], None] = 'c1d220260038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.add_column(sa.Column('category', sa.String(length=10), nullable=False, server_default='general'))
        batch.add_column(sa.Column('priority', sa.String(length=10), nullable=False, server_default='normal'))


def downgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.drop_column('priority')
        batch.drop_column('category')
