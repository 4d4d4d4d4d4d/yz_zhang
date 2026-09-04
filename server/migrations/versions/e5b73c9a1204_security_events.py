"""security: events, cross-replica bans

Revision ID: e5b73c9a1204
Revises: d29e6a41f80b
Create Date: 2026-08-27 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b73c9a1204'
down_revision: Union[str, Sequence[str], None] = 'd29e6a41f80b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'security_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('scope', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_security_events_kind'), 'security_events', ['kind'])
    op.create_index(op.f('ix_security_events_ip'), 'security_events', ['ip'])
    op.create_index(op.f('ix_security_events_created_at'), 'security_events', ['created_at'])
    op.create_index(op.f('ix_security_events_expires_at'), 'security_events', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_security_events_expires_at'), table_name='security_events')
    op.drop_index(op.f('ix_security_events_created_at'), table_name='security_events')
    op.drop_index(op.f('ix_security_events_ip'), table_name='security_events')
    op.drop_index(op.f('ix_security_events_kind'), table_name='security_events')
    op.drop_table('security_events')
