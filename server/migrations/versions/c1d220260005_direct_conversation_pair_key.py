"""direct conversation pair key

IM-052 给单聊的「参与者对」一个规范化唯一键。

`participants` 是 JSON，数据库没法在它上面建唯一约束，于是
`get_or_create_direct` 的 check-then-insert 没有任何东西兜底——并发会建出
两条单聊会话。探针实测：并发 10 次开同一个单聊，库里留下两行 `[1, 2]`。

**这个迁移刻意是非破坏性的。**

存量库里可能已经有重复的单聊对。给最早的那一条（id 最小）填上键，
**重复的那些留 NULL**：

- 消息一条不动、会话行一条不删——两条线上的历史都还在，
  会话列表按 `participants` 查，所以用户仍然看得到它们；
- 以后的查找会收敛到那一条有键的上面，新消息不再继续分叉。

另一条路是把重复会话的消息并到最早那条再删掉多余的行。没有这么做：
**在迁移里合并用户的聊天记录是不可逆的**，而且 `ConversationRead` 的已读
位点会一起错位。分叉已经发生了，先把它止住；要不要合并是产品决定，
不是一次 schema 变更该顺手做的事。

Revision ID: c1d220260005
Revises: b0a120260004
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d220260005'
down_revision: Union[str, Sequence[str], None] = 'b0a120260004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("direct_key", sa.String(40), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, participants FROM conversations WHERE kind = 'direct' ORDER BY id"
    )).fetchall()

    import json

    seen: set[str] = set()
    for row_id, participants in rows:
        try:
            ids = sorted({int(x) for x in json.loads(participants or "[]")})
        except (ValueError, TypeError):
            continue
        if len(ids) != 2:
            # 参与者不是两个人的「单聊」是坏数据，不给它键：
            # 硬塞一个键会让唯一约束把两条不相干的行判成冲突
            continue
        key = f"{ids[0]}-{ids[1]}"
        if key in seen:
            continue  # 重复对：留 NULL，历史不动（见模块 docstring）
        seen.add(key)
        conn.execute(
            sa.text("UPDATE conversations SET direct_key = :k WHERE id = :i"),
            {"k": key, "i": row_id},
        )

    # 唯一索引放在回填之后：先建索引会被存量重复数据顶回来
    op.create_index("ix_conversations_direct_key", "conversations",
                    ["direct_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_conversations_direct_key", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("direct_key")
