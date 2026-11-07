"""support_local_holidays

ESCA-073（V332，305 号 spec）：地区性假日，只对所在地区相同的客服起作用；客服多一个所在地区。

Revision ID: c1d220260077
Revises: c1d220260076
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260077'
down_revision: Union[str, Sequence[str], None] = 'c1d220260076'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_local_holidays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('region', sa.String(length=20), nullable=False),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('day', 'region'),
    )
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.add_column(sa.Column('region', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('support_agent_scopes') as batch:
        batch.drop_column('region')
    op.drop_table('support_local_holidays')
