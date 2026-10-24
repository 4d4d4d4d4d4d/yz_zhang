"""ticket escalation

ESCA-051（V178，150 号 spec）：工单认领与超时升级级别。

Revision ID: c1d220260028
Revises: c1d220260027
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260028'
down_revision: Union[str, Sequence[str], None] = 'c1d220260027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.add_column(sa.Column('assignee_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('claimed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('escalated_at', sa.DateTime(), nullable=True))
        batch.create_index(batch.f('ix_tickets_assignee_id'), ['assignee_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.drop_index(batch.f('ix_tickets_assignee_id'))
        batch.drop_column('escalated_at')
        batch.drop_column('escalation_level')
        batch.drop_column('claimed_at')
        batch.drop_column('assignee_id')
