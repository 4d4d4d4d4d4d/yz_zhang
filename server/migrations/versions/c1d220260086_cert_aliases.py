"""cert_aliases

SCN-213（V361，334 号 spec）：运营在后台配的资质别名（四眼）。

Revision ID: c1d220260086
Revises: c1d220260085
Create Date: 2026-10-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260086'
down_revision: Union[str, Sequence[str], None] = 'c1d220260085'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cert_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name_a', sa.String(length=30), nullable=False),
        sa.Column('name_b', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('proposed_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('cert_aliases')
