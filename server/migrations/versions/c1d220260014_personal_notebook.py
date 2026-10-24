"""personal notebook (knowledge base)

KB-100~110（V147，122 号 spec）：个人知识库的笔记与个人方法。全是本人私有数据。

Revision ID: c1d220260014
Revises: c1d220260013
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260014'
down_revision: Union[str, Sequence[str], None] = 'c1d220260013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'nb_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('pinned', sa.Boolean(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_nb_notes_owner_id', 'nb_notes', ['owner_id'])
    op.create_index('ix_nb_notes_status', 'nb_notes', ['status'])
    op.create_index('ix_nb_notes_updated_at', 'nb_notes', ['updated_at'])
    op.create_table(
        'nb_methods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('source_note_ids', sa.JSON(), nullable=False),
        sa.Column('uses', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_nb_methods_owner_id', 'nb_methods', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_nb_methods_owner_id', table_name='nb_methods')
    op.drop_table('nb_methods')
    op.drop_index('ix_nb_notes_updated_at', table_name='nb_notes')
    op.drop_index('ix_nb_notes_status', table_name='nb_notes')
    op.drop_index('ix_nb_notes_owner_id', table_name='nb_notes')
    op.drop_table('nb_notes')
