"""KB-100 个人知识库（122 号 spec）：收件箱、笔记 / 链接 / 纪要、标签、个人方法。

与平台经验库（`knowledge` 模块：类目卡片、FAQ、经验单元）是两回事：
这里的每一条都**只属于本人**——不公开、不进全局搜索、不进推荐、不进经验库、不送去向量化供应商。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class NbNote(Base):
    __tablename__ = "nb_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="note")       # note / link / minutes
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    # inbox：随手记进来还没整理；filed：整理过；archived：不再常用但留着
    status: Mapped[str] = mapped_column(String(16), default="inbox", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 归到工作台的哪个项目
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class NbMethod(Base):
    """个人方法：从笔记里蒸馏出来的、可以反复套用的步骤清单（蓝皮书第 5、22 章的个人版 Skill）。"""
    __tablename__ = "nb_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(500), default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)               # [{title, note}]
    source_note_ids: Mapped[list] = mapped_column(JSON, default=list)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
