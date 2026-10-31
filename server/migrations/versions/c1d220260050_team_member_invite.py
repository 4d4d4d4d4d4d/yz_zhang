"""team_member_invite

TEAM-068（V255，228 号 spec）：成员通过哪条邀请链接加入的。

Revision ID: c1d220260050
Revises: c1d220260049
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260050'
down_revision: Union[str, Sequence[str], None] = 'c1d220260049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('team_members') as batch:
        batch.add_column(sa.Column('invite_id', sa.Integer(), nullable=True))
        batch.create_index('ix_team_members_invite_id', ['invite_id'])


def downgrade() -> None:
    with op.batch_alter_table('team_members') as batch:
        batch.drop_index('ix_team_members_invite_id')
        batch.drop_column('invite_id')
