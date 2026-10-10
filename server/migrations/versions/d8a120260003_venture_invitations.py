"""Persist actual membership authorization instead of trusting knowledge of an ID."""
from alembic import op
import sqlalchemy as sa

revision = 'd8a120260003'
down_revision = 'c7e1f2a90b34'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('venture_invitations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venture_id', sa.Integer(), nullable=False),
        sa.Column('invitee_id', sa.Integer(), nullable=False),
        sa.Column('inviter_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('venture_id', 'invitee_id', name='uq_venture_invitee'))
    op.create_index('ix_venture_invitations_venture_id', 'venture_invitations', ['venture_id'])
    op.create_index('ix_venture_invitations_invitee_id', 'venture_invitations', ['invitee_id'])


def downgrade():
    op.drop_table('venture_invitations')
