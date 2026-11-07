"""gig worker tools: availability and saved places

GIG-100~109（V150，125 号 spec）：「现在有空」（粗化位置、到点失效）与常用地点。

Revision ID: c1d220260017
Revises: c1d220260016
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260017'
down_revision: Union[str, Sequence[str], None] = 'c1d220260016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gig_availability',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('until', sa.DateTime(), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('radius_km', sa.Integer(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('pushed', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_index('ix_gig_availability_until', 'gig_availability', ['until'])
    op.create_table(
        'gig_places',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gig_places_owner_id', 'gig_places', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_gig_places_owner_id', table_name='gig_places')
    op.drop_table('gig_places')
    op.drop_index('ix_gig_availability_until', table_name='gig_availability')
    op.drop_table('gig_availability')
