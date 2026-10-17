from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Decomposition(Base):
    """AI-DEC-010/011 分解提案：AI 产出草稿，用户编辑确认后才生成子任务。"""

    __tablename__ = "decompositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    creator_id: Mapped[int] = mapped_column(Integer)
    # items: [{title, description, required_skills, budget_cents, depends_on_idx: [int]}]
    items: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed/confirmed/discarded
    source: Mapped[str] = mapped_column(String(40), default="")
    # AI-DEC-040~048（V132，106 号 spec）整棵树的节点表；为空表示这是 V132 之前的
    # 一层提案，仍按 `items` 走。节点字段见 `tree.py` 的 `new_node`。
    tree: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # 逐层展开与逐点编辑都是「读整棵树 → 改 → 写回」：比较并交换这个计数
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # AI-DEC-045 成本上限：这棵树调了几次模型
    model_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
