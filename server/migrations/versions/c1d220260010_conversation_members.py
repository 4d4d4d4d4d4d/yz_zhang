"""conversation members index

CONC-066（V140，115 号 spec）：`conversations.participants` 是 JSON 列表、查不了索引，
「我参与的会话」原来要把全平台会话读出来在 Python 里挑。新增按 user_id 索引的成员表，
并从现有 participants 回填。之后由 ORM flush 事件自动与 participants 对齐。

Revision ID: c1d220260010
Revises: c1d220260009
Create Date: 2026-10-13 00:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260010'
down_revision: Union[str, Sequence[str], None] = 'c1d220260009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversation_members',
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('conversation_id', 'user_id'),
    )
    op.create_index('ix_conversation_members_user_id', 'conversation_members', ['user_id'])
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, participants FROM conversations")).fetchall()
    members = []
    for cid, parts in rows:
        if isinstance(parts, str):
            parts = json.loads(parts or "[]")
        for uid in sorted({int(u) for u in (parts or [])}):
            members.append({"c": cid, "u": uid})
    if members:
        conn.execute(sa.text("INSERT INTO conversation_members (conversation_id, user_id) VALUES (:c, :u)"), members)


def downgrade() -> None:
    op.drop_index('ix_conversation_members_user_id', table_name='conversation_members')
    op.drop_table('conversation_members')
