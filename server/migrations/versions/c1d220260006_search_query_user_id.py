"""search queries: user id and purge of stored identifiers

SRCH-003 / PRIV-060 热词与联想此前**原样公开任何人敲过的原始搜索串**，
不要登录、不设门槛、不过审核：有人搜过「张三 13800001234」，任何人在框里
打「张」都能看到它——一次就够。

这一版：
- 加 `user_id`：公开的热词与联想只算**至少 N 个不同的人**搜过的词
  （k-匿名的门槛；一个人的搜索永远不会被公开）。存量行没有 user_id，
  不计入任何人数——它们从此不会再被公开。
- **删掉已经存下的身份标识类搜索词**（手机号、身份证号、邮箱）。

第二条是不可逆的，而 V118 那次我拒绝在迁移里合并聊天记录，理由也正是
「不可逆」。区别在于对象：那是**用户的聊天记录**，是他们的东西；
这是**平台内部的统计日志**，里面的身份标识本来就不该被存下来——
留着它们没有任何正当用途，只是一份负债。删掉它们不会让任何人失去什么。

Revision ID: c1d220260006
Revises: c1d220260005
Create Date: 2026-10-12 00:00:00.000000

"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260006'
down_revision: Union[str, Sequence[str], None] = 'c1d220260005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 与 app/modules/analytics/service.py 的 PII_PATTERNS 一致。
# 迁移不 import 应用代码（迁移要能在任何一个历史版本的代码上跑），所以抄一份；
# 一致性由 test_search_privacy 钉住。
PII_PATTERNS = (
    r"(?<!\d)1[3-9]\d{9}(?!\d)",                 # 手机号
    r"(?<!\d)\d{17}[\dXx](?![\dXx])",            # 18 位身份证号
    r"(?<!\d)\d{15}(?!\d)",                      # 15 位身份证号
    r"[\w.+-]+@[\w-]+\.[\w.-]+",                 # 邮箱
)


def upgrade() -> None:
    with op.batch_alter_table("search_queries") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_search_queries_user_id", ["user_id"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, term FROM search_queries")).fetchall()
    compiled = [re.compile(p) for p in PII_PATTERNS]
    doomed = [rid for rid, term in rows if any(p.search(term or "") for p in compiled)]
    for i in range(0, len(doomed), 500):
        chunk = doomed[i:i + 500]
        conn.execute(
            sa.text(f"DELETE FROM search_queries WHERE id IN ({','.join(str(x) for x in chunk)})")
        )


def downgrade() -> None:
    # 删掉的身份标识不恢复——它们本来就不该存在（见模块 docstring）
    with op.batch_alter_table("search_queries") as batch:
        batch.drop_index("ix_search_queries_user_id")
        batch.drop_column("user_id")
