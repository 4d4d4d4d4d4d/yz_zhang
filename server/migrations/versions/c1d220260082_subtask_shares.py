"""subtask_shares

AI-DEC-024（V348，321 号 spec）：前一步的交付人把成果开放给后一步的执行者。

Revision ID: c1d220260082
Revises: c1d220260081
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260082'
down_revision: Union[str, Sequence[str], None] = 'c1d220260081'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subtask_shares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('from_task_id', sa.Integer(), nullable=False),
        sa.Column('to_task_id', sa.Integer(), nullable=False),
        sa.Column('granted_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subtask_shares_from_task_id'), 'subtask_shares', ['from_task_id'], unique=False)
    op.create_index(op.f('ix_subtask_shares_to_task_id'), 'subtask_shares', ['to_task_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subtask_shares_to_task_id'), table_name='subtask_shares')
    op.drop_index(op.f('ix_subtask_shares_from_task_id'), table_name='subtask_shares')
    op.drop_table('subtask_shares')
