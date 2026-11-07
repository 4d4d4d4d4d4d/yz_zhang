"""Unanimous consent for project payouts."""
from alembic import op
import sqlalchemy as sa
revision='a9a120260003'
down_revision='f8a120260003'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('payout_proposals',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('venture_id',sa.Integer(),nullable=False),
        sa.Column('created_by',sa.Integer(),nullable=False),
        sa.Column('amount_cents',sa.Integer(),nullable=False),
        sa.Column('memo',sa.String(200),nullable=False),
        sa.Column('member_ids',sa.JSON(),nullable=False),
        sa.Column('share_snapshot',sa.JSON(),nullable=False),
        sa.Column('approvals',sa.JSON(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('distribution_id',sa.Integer(),nullable=True),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('expires_at',sa.DateTime(),nullable=False))
    op.create_index('ix_payout_proposals_venture_id','payout_proposals',['venture_id'])


def downgrade():
    op.drop_table('payout_proposals')
