"""one-person company books and profile

OPC-100~109（V149，124 号 spec）：一人公司的主体设置与记账底稿。本人私有。

Revision ID: c1d220260016
Revises: c1d220260015
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260016'
down_revision: Union[str, Sequence[str], None] = 'c1d220260015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opc_profiles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('entity', sa.String(length=16), nullable=False),
        sa.Column('vat', sa.String(length=16), nullable=False),
        sa.Column('vat_period', sa.String(length=8), nullable=False),
        sa.Column('small_low_profit', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'opc_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('tax_cents', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('counterparty', sa.String(length=60), nullable=False),
        sa.Column('invoice_no', sa.String(length=40), nullable=False),
        sa.Column('invoice_kind', sa.String(length=12), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('source_ref', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'source_ref', name='uq_opc_entry_source'),
    )
    op.create_index('ix_opc_entries_owner_id', 'opc_entries', ['owner_id'])
    op.create_index('ix_opc_entries_occurred_on', 'opc_entries', ['occurred_on'])


def downgrade() -> None:
    op.drop_index('ix_opc_entries_occurred_on', table_name='opc_entries')
    op.drop_index('ix_opc_entries_owner_id', table_name='opc_entries')
    op.drop_table('opc_entries')
    op.drop_table('opc_profiles')
