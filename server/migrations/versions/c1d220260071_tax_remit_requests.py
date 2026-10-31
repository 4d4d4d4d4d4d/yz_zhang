"""tax_remit_requests

PAY-042d（V314，287 号 spec）：大额待缴税款的缴库草稿，财务确认后才划出。

Revision ID: c1d220260071
Revises: c1d220260070
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260071'
down_revision: Union[str, Sequence[str], None] = 'c1d220260070'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tax_remit_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decision_reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tax_remit_requests_status'), 'tax_remit_requests', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tax_remit_requests_status'), table_name='tax_remit_requests')
    op.drop_table('tax_remit_requests')
