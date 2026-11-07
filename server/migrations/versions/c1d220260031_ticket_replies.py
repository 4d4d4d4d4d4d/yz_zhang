"""ticket replies

ESCA-053 / ESCA-054（V183，157 号 spec）：工单往来、首次响应时间与首次响应超时提醒。

Revision ID: c1d220260031
Revises: c1d220260030
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260031'
down_revision: Union[str, Sequence[str], None] = 'c1d220260030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.add_column(sa.Column('first_response_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('first_response_alerted_at', sa.DateTime(), nullable=True))
    op.create_table(
        'ticket_replies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('is_staff', sa.Boolean(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ticket_replies') as batch:
        batch.create_index(batch.f('ix_ticket_replies_ticket_id'), ['ticket_id'], unique=False)


def downgrade() -> None:
    op.drop_table('ticket_replies')
    with op.batch_alter_table('tickets') as batch:
        batch.drop_column('first_response_alerted_at')
        batch.drop_column('first_response_at')
