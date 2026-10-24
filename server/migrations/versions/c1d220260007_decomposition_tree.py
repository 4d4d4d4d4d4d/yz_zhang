"""decomposition tree: nodes, revision, model call counter; seed template deliverables

AI-DEC-040~048（V132，106 号 spec，设计见 96 号）：一次分解从「一层待办」变成
「逐层展开、每个叶子说清谁能闭环的树」。

- `decompositions.tree`：整棵树的节点表（JSON，≤ 60 个节点）。存量提案的 `tree`
  为空，仍按原来的一层 `items` 走——不改写用户已有的草稿。
- `decompositions.revision`：逐层展开与逐点编辑都是「读整棵树 → 改 → 写回」，
  两个并发请求会互相覆盖；比较并交换这个计数。
- `decompositions.model_calls`：每棵树调了几次模型（成本上限，AI-DEC-045）。
- 种子分解模板的每一步补上「交付物」与「验收标准」：没有这两样的节点不能算叶子。
  只补**标题与种子一致、且还没有这两个字段**的步骤——运营改过的不动。

Revision ID: c1d220260007
Revises: c1d220260006
Create Date: 2026-10-12 00:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260007'
down_revision: Union[str, Sequence[str], None] = 'c1d220260006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 与 app/modules/knowledge/service.py 的 SEED_TEMPLATES 一致（迁移不 import 应用代码）；
# 一致性由 test_decompose_tree 钉住。
SEED_LEAF_FIELDS = {
    "需求梳理与原型设计": ("需求文档与可点击原型", "发布方逐页确认原型覆盖了全部需求点"),
    "UI 视觉设计": ("全部页面的视觉稿与切图", "视觉稿页面数与原型一致，发布方确认风格"),
    "前端开发": ("可部署的前端代码与构建说明", "在测试环境按原型逐页走通，与视觉稿一致"),
    "后端开发": ("接口服务代码、接口文档与部署说明", "接口文档里的每个接口在测试环境可调用并返回约定结构"),
    "联调测试与上线": ("测试报告与线上可访问的地址", "测试报告无未关闭的严重缺陷，线上地址可正常使用"),
    "方案策划与预算": ("活动方案与分项预算表", "发布方确认方案与预算"),
    "物料设计制作": ("方案列出的全部物料实物或印刷文件", "物料清单逐项点验，数量与规格相符"),
    "现场执行": ("按方案完成的活动与现场照片", "活动按方案时间与流程完成，发布方现场或凭照片确认"),
}


def upgrade() -> None:
    with op.batch_alter_table('decompositions') as batch:
        batch.add_column(sa.Column('tree', sa.JSON(), nullable=False, server_default='[]'))
        batch.add_column(sa.Column('revision', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('model_calls', sa.Integer(), nullable=False, server_default='0'))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, items FROM decomposition_templates")).fetchall()
    for tid, raw in rows:
        items = json.loads(raw) if isinstance(raw, str) else (raw or [])
        changed = False
        for it in items:
            seed = SEED_LEAF_FIELDS.get(it.get("title", ""))
            if seed and not it.get("deliverable") and not it.get("acceptance"):
                it["deliverable"], it["acceptance"] = seed
                changed = True
        if changed:
            conn.execute(sa.text("UPDATE decomposition_templates SET items = :i WHERE id = :id"),
                         {"i": json.dumps(items, ensure_ascii=False), "id": tid})


def downgrade() -> None:
    with op.batch_alter_table('decompositions') as batch:
        batch.drop_column('model_calls')
        batch.drop_column('revision')
        batch.drop_column('tree')
