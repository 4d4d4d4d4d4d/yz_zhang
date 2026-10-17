"""aml: suspicious activity records

Revision ID: d29e6a41f80b
Revises: c4f8b2d17e35
Create Date: 2026-08-26 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd29e6a41f80b'
down_revision: Union[str, Sequence[str], None] = 'c4f8b2d17e35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'suspicious_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.String(length=32), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('amount_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ref_type', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('ref_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_suspicious_activities_user_id'), 'suspicious_activities', ['user_id'])
    op.create_index(op.f('ix_suspicious_activities_pattern'), 'suspicious_activities', ['pattern'])
    op.create_index(op.f('ix_suspicious_activities_status'), 'suspicious_activities', ['status'])
    op.create_index(op.f('ix_suspicious_activities_created_at'), 'suspicious_activities',
                    ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_suspicious_activities_created_at'), table_name='suspicious_activities')
    op.drop_index(op.f('ix_suspicious_activities_status'), table_name='suspicious_activities')
    op.drop_index(op.f('ix_suspicious_activities_pattern'), table_name='suspicious_activities')
    op.drop_index(op.f('ix_suspicious_activities_user_id'), table_name='suspicious_activities')
    op.drop_table('suspicious_activities')
