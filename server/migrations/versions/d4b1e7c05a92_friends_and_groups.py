"""im: friendships and group chat (IM-003/020/021)

原始 spec 里写得很明确：加好友「双向同意」、群成员「上限可配」。
两条都是反骚扰的地基，不是锦上添花。

Revision ID: d4b1e7c05a92
Revises: c93f5a2e8d17
Create Date: 2026-09-16 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b1e7c05a92'
down_revision: Union[str, Sequence[str], None] = 'c93f5a2e8d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'friendships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('addressee_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('requester_remark', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('addressee_remark', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # 一对人只能有一条：双方同时发起会攒出两条，接受哪一条都对，
        # 而另一条永远悬着
        sa.UniqueConstraint('requester_id', 'addressee_id'),
    )
    op.create_index('ix_friendships_requester_id', 'friendships', ['requester_id'])
    op.create_index('ix_friendships_addressee_id', 'friendships', ['addressee_id'])

    op.add_column('conversations', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.add_column('conversations', sa.Column(
        'name', sa.String(length=50), nullable=False, server_default=''))
    op.add_column('conversations', sa.Column(
        'announcement', sa.String(length=500), nullable=False, server_default=''))
    op.add_column('conversations', sa.Column('muted', sa.JSON(), nullable=True))
    op.execute("UPDATE conversations SET muted = '[]' WHERE muted IS NULL")
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.alter_column('muted', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    for col in ('muted', 'announcement', 'name', 'owner_id'):
        op.drop_column('conversations', col)
    op.drop_index('ix_friendships_addressee_id', table_name='friendships')
    op.drop_index('ix_friendships_requester_id', table_name='friendships')
    op.drop_table('friendships')
