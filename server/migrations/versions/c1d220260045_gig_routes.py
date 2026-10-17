"""gig_routes

SCN-140（V236，208 号 spec）：接单者的常用路线（哪几天、几点、从哪到哪），到点前推顺路的名额。
不存坐标（坐标在已粗化的常用地点上）。

Revision ID: c1d220260045
Revises: c1d220260044
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260045'
down_revision: Union[str, Sequence[str], None] = 'c1d220260044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gig_routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('from_place_id', sa.Integer(), nullable=False),
        sa.Column('to_place_id', sa.Integer(), nullable=False),
        sa.Column('weekdays', sa.JSON(), nullable=False),
        sa.Column('depart_hm', sa.String(length=5), nullable=False),
        sa.Column('within_hours', sa.Integer(), nullable=False),
        sa.Column('last_pushed_on', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_gig_routes_owner_id'), 'gig_routes', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_gig_routes_owner_id'), table_name='gig_routes')
    op.drop_table('gig_routes')
