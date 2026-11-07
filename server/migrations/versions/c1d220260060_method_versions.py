"""method_versions

AGT-098（V271，244 号 spec）：方法的版本历史。

Revision ID: c1d220260060
Revises: c1d220260059
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260060'
down_revision: Union[str, Sequence[str], None] = 'c1d220260059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'nb_method_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('method_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('replaced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_nb_method_versions_method_id'), 'nb_method_versions', ['method_id'], unique=False)
    op.create_index(op.f('ix_nb_method_versions_owner_id'), 'nb_method_versions', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_nb_method_versions_owner_id'), table_name='nb_method_versions')
    op.drop_index(op.f('ix_nb_method_versions_method_id'), table_name='nb_method_versions')
    op.drop_table('nb_method_versions')
