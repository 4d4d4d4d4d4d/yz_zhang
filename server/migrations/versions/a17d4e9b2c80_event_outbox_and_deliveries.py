"""events: transactional outbox and delivery records

Revision ID: a17d4e9b2c80
Revises: 8c31a0be47f2
Create Date: 2026-08-25 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a17d4e9b2c80'
down_revision: Union[str, Sequence[str], None] = '8c31a0be47f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=48), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('instance', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outbox_events_event'), 'outbox_events', ['event'])
    op.create_index(op.f('ix_outbox_events_created_at'), 'outbox_events', ['created_at'])

    op.create_table(
        'event_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=48), nullable=False),
        sa.Column('handler', sa.String(length=120), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='done'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_error', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # EVT-002 「恰好一次」不是靠代码自觉，是靠这个约束——跨副本同样成立
        sa.UniqueConstraint('event_id', 'handler', name='uq_delivery_event_handler'),
    )
    op.create_index(op.f('ix_event_deliveries_event_id'), 'event_deliveries', ['event_id'])
    op.create_index(op.f('ix_event_deliveries_event'), 'event_deliveries', ['event'])
    op.create_index(op.f('ix_event_deliveries_handler'), 'event_deliveries', ['handler'])
    op.create_index(op.f('ix_event_deliveries_status'), 'event_deliveries', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_event_deliveries_status'), table_name='event_deliveries')
    op.drop_index(op.f('ix_event_deliveries_handler'), table_name='event_deliveries')
    op.drop_index(op.f('ix_event_deliveries_event'), table_name='event_deliveries')
    op.drop_index(op.f('ix_event_deliveries_event_id'), table_name='event_deliveries')
    op.drop_table('event_deliveries')
    op.drop_index(op.f('ix_outbox_events_created_at'), table_name='outbox_events')
    op.drop_index(op.f('ix_outbox_events_event'), table_name='outbox_events')
    op.drop_table('outbox_events')
