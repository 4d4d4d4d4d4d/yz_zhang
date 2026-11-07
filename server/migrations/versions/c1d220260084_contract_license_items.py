"""contract_license_items

SCN-202（V356，329 号 spec）：交付附授权清单。

Revision ID: c1d220260084
Revises: c1d220260083
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260084'
down_revision: Union[str, Sequence[str], None] = 'c1d220260083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contract_license_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('source', sa.String(length=120), nullable=False),
        sa.Column('scope', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contract_license_items_contract_id'), 'contract_license_items', ['contract_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_contract_license_items_contract_id'), table_name='contract_license_items')
    op.drop_table('contract_license_items')
