"""contract_handover_items

SCN-205（V357，330 号 spec）：建站交付的账号交接清单。

Revision ID: c1d220260085
Revises: c1d220260084
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260085'
down_revision: Union[str, Sequence[str], None] = 'c1d220260084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contract_handover_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('note', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contract_handover_items_contract_id'), 'contract_handover_items', ['contract_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_contract_handover_items_contract_id'), table_name='contract_handover_items')
    op.drop_table('contract_handover_items')
