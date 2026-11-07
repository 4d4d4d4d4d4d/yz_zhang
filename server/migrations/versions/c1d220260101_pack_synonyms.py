"""pack_synonyms

PACK-092c（V463，436 号 spec）：运营在后台加的场景包近义说法（四眼）。

Revision ID: c1d220260101
Revises: c1d220260100
Create Date: 2026-11-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260101'
down_revision: Union[str, Sequence[str], None] = 'c1d220260100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pack_synonyms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=12), nullable=False),
        sa.Column('words', sa.JSON(), nullable=False),
        sa.Column('includes', sa.JSON(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('proposed_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('pack_synonyms')
