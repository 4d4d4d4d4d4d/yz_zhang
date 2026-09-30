"""tax: withholding records and invoice requests

Revision ID: c4f8b2d17e35
Revises: a17d4e9b2c80
Create Date: 2026-08-25 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8b2d17e35'
down_revision: Union[str, Sequence[str], None] = 'a17d4e9b2c80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tax_withholdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('settlement_kind', sa.String(length=24), nullable=False,
                  server_default='release'),
        sa.Column('income_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('taxable_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('withheld_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rule', sa.String(length=32), nullable=False, server_default='none'),
        sa.Column('mode', sa.String(length=16), nullable=False, server_default='none'),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tax_withholdings_user_id'), 'tax_withholdings', ['user_id'])
    op.create_index(op.f('ix_tax_withholdings_contract_id'), 'tax_withholdings', ['contract_id'])
    op.create_index(op.f('ix_tax_withholdings_created_at'), 'tax_withholdings', ['created_at'])

    op.create_table(
        'invoice_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('title', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('tax_no', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoice_requests_kind'), 'invoice_requests', ['kind'])
    op.create_index(op.f('ix_invoice_requests_requester_id'), 'invoice_requests', ['requester_id'])
    op.create_index(op.f('ix_invoice_requests_contract_id'), 'invoice_requests', ['contract_id'])
    op.create_index(op.f('ix_invoice_requests_status'), 'invoice_requests', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_invoice_requests_status'), table_name='invoice_requests')
    op.drop_index(op.f('ix_invoice_requests_contract_id'), table_name='invoice_requests')
    op.drop_index(op.f('ix_invoice_requests_requester_id'), table_name='invoice_requests')
    op.drop_index(op.f('ix_invoice_requests_kind'), table_name='invoice_requests')
    op.drop_table('invoice_requests')
    op.drop_index(op.f('ix_tax_withholdings_created_at'), table_name='tax_withholdings')
    op.drop_index(op.f('ix_tax_withholdings_contract_id'), table_name='tax_withholdings')
    op.drop_index(op.f('ix_tax_withholdings_user_id'), table_name='tax_withholdings')
    op.drop_table('tax_withholdings')
