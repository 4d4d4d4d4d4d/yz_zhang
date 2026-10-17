"""sandbox model catalog

SBX-106（V158，128 号 spec）：端侧量化小模型目录（四眼上架、必须有 sha256）。

Revision ID: c1d220260019
Revises: c1d220260018
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260019'
down_revision: Union[str, Sequence[str], None] = 'c1d220260018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sandbox_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('family', sa.String(length=60), nullable=False),
        sa.Column('params_b', sa.Float(), nullable=False),
        sa.Column('quant', sa.String(length=20), nullable=False),
        sa.Column('file_format', sa.String(length=20), nullable=False),
        sa.Column('size_mb', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('license', sa.String(length=100), nullable=False),
        sa.Column('min_ram_gb', sa.Float(), nullable=False),
        sa.Column('languages', sa.JSON(), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('retired_reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_index('ix_sandbox_models_status', 'sandbox_models', ['status'])


def downgrade() -> None:
    op.drop_index('ix_sandbox_models_status', table_name='sandbox_models')
    op.drop_table('sandbox_models')
