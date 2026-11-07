"""finance_period_corrections

FIN-064（V292，265 号 spec）：已锁月份的更正说明（四眼）。

Revision ID: c1d220260066
Revises: c1d220260065
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260066'
down_revision: Union[str, Sequence[str], None] = 'c1d220260065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'finance_period_corrections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=False),
        sa.Column('amount_delta_cents', sa.Integer(), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decision_reason', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('finance_period_corrections') as batch:
        batch.create_index(batch.f('ix_finance_period_corrections_period'), ['period'], unique=False)
        batch.create_index(batch.f('ix_finance_period_corrections_requested_by'), ['requested_by'], unique=False)
        batch.create_index(batch.f('ix_finance_period_corrections_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('finance_period_corrections') as batch:
        batch.drop_index(batch.f('ix_finance_period_corrections_status'))
        batch.drop_index(batch.f('ix_finance_period_corrections_requested_by'))
        batch.drop_index(batch.f('ix_finance_period_corrections_period'))
    op.drop_table('finance_period_corrections')
