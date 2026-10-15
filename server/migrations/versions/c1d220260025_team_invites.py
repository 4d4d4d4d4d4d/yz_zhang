"""team invites

TEAM-066（V175，147 号 spec）：团队邀请链接（只存令牌哈希、有效期、使用次数上限、可作废）。

Revision ID: c1d220260025
Revises: c1d220260024
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260025'
down_revision: Union[str, Sequence[str], None] = 'c1d220260024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'team_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('spend_limit_cents', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('uses', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_team_invites_team_id'), 'team_invites', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_invites_token_hash'), 'team_invites', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_invites_token_hash'), table_name='team_invites')
    op.drop_index(op.f('ix_team_invites_team_id'), table_name='team_invites')
    op.drop_table('team_invites')
