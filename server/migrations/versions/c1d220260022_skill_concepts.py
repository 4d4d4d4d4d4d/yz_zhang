"""skill concepts

SKL-101（V155，135 号 spec）：技能概念表的后台增改（种子在仓库里）。

Revision ID: c1d220260022
Revises: c1d220260021
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260022'
down_revision: Union[str, Sequence[str], None] = 'c1d220260021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'skill_concepts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=40), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('skill_concepts')
