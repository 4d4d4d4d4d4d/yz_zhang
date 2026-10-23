"""support_holidays

ESCA-070（V302，276 号 spec）：客服排班用的节假日 / 调休日历。

Revision ID: c1d220260069
Revises: c1d220260068
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260069'
down_revision: Union[str, Sequence[str], None] = 'c1d220260068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_holidays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('as_weekday', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('day'),
    )


def downgrade() -> None:
    op.drop_table('support_holidays')
