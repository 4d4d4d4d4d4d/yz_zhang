"""support_agent_scopes

ESCA-061（V261，234 号 spec）：客服自己声明负责哪几类工单。

Revision ID: c1d220260052
Revises: c1d220260051
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260052'
down_revision: Union[str, Sequence[str], None] = 'c1d220260051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_agent_scopes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_agent_scopes_user_id', 'support_agent_scopes', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_support_agent_scopes_user_id', table_name='support_agent_scopes')
    op.drop_table('support_agent_scopes')
