"""orchestrator experience tools and agent audit

AGT-084 / REL-110（V154，131 号 spec）：编排授权调用经验工具（草稿挂在步骤上）、调用记录写明 agent 身份与是否采用。

Revision ID: c1d220260021
Revises: c1d220260020
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260021'
down_revision: Union[str, Sequence[str], None] = 'c1d220260020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('unit_invocations') as b:
        b.add_column(sa.Column('agent', sa.String(length=60), nullable=False, server_default=''))
        b.add_column(sa.Column('adopted', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('missions') as b:
        b.add_column(sa.Column('allow_tools', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('mission_steps') as b:
        b.add_column(sa.Column('tool_drafts', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table('mission_steps') as b:
        b.drop_column('tool_drafts')
    with op.batch_alter_table('missions') as b:
        b.drop_column('allow_tools')
    with op.batch_alter_table('unit_invocations') as b:
        b.drop_column('adopted')
        b.drop_column('agent')
