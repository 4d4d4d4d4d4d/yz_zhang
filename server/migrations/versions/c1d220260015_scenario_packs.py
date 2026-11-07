"""scenario packs and platform assets

PACK-100~109（V148，123 号 spec）：场景包（版本、审核、上线）、用户启用记录、使用事件。

Revision ID: c1d220260015
Revises: c1d220260014
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260015'
down_revision: Union[str, Sequence[str], None] = 'c1d220260014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scenario_packs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('segment', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('retired_reason', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', 'version', name='uq_scenario_pack_version'),
    )
    op.create_index('ix_scenario_packs_key', 'scenario_packs', ['key'])
    op.create_index('ix_scenario_packs_status', 'scenario_packs', ['status'])
    op.create_table(
        'pack_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('pack_key', sa.String(length=60), nullable=False),
        sa.Column('pack_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('installed', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'pack_key', name='uq_pack_enrollment_user_key'),
    )
    op.create_index('ix_pack_enrollments_user_id', 'pack_enrollments', ['user_id'])
    op.create_index('ix_pack_enrollments_pack_key', 'pack_enrollments', ['pack_key'])
    op.create_index('ix_pack_enrollments_pack_id', 'pack_enrollments', ['pack_id'])
    op.create_table(
        'pack_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pack_key', sa.String(length=60), nullable=False),
        sa.Column('pack_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pack_events_pack_key', 'pack_events', ['pack_key'])
    op.create_index('ix_pack_events_user_id', 'pack_events', ['user_id'])
    op.create_index('ix_pack_events_created_at', 'pack_events', ['created_at'])


def downgrade() -> None:
    for ix in ('ix_pack_events_created_at', 'ix_pack_events_user_id', 'ix_pack_events_pack_key'):
        op.drop_index(ix, table_name='pack_events')
    op.drop_table('pack_events')
    for ix in ('ix_pack_enrollments_pack_id', 'ix_pack_enrollments_pack_key', 'ix_pack_enrollments_user_id'):
        op.drop_index(ix, table_name='pack_enrollments')
    op.drop_table('pack_enrollments')
    op.drop_index('ix_scenario_packs_status', table_name='scenario_packs')
    op.drop_index('ix_scenario_packs_key', table_name='scenario_packs')
    op.drop_table('scenario_packs')
