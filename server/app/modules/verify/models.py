"""VER 人类核验闭环的数据模型（49 号 spec）。

核验是**独立实体**而不是一个 Task。判断标准与 V73「agent 复用 User」同一条：
复用能省掉重复实现的就复用，复用只能带来仪式的就不复用。

- V73 复用 User：托管/纠纷/信用/账本全部以 user_id 为键，不复用得各写第二遍。
- 这里不复用 Task：核验是一笔 ¥10~50 的活，而且常见情形下**付款方是平台自己**，
  让平台对自己做资金托管，是用重机制办轻事。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 结论三档。**没有「部分通过」**：发布方拿到它之后不知道该干什么，
# 而不可执行的结论等于没有结论。
OUTCOMES = ("approved", "revised", "rejected")
# 解除原任务交付闸门的两档
UNBLOCKING_OUTCOMES = ("approved", "revised")


class VerificationOrder(Base):
    __tablename__ = "verification_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # VER-002 谁掏钱是个有立场的判断：
    # agent 置信度不足是**平台的问题**，不该让发布方为 AI 的不确定性买单。
    # payer_id = 0（平台）或发布方 user_id。
    payer_id: Mapped[int] = mapped_column(Integer, index=True)
    trigger: Mapped[str] = mapped_column(String(20))   # escalation / requested
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)

    verifier_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # open（待接单）/ claimed（已接单）/ done / cancelled / expired
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)

    outcome: Mapped[str] = mapped_column(String(12), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    revised_output: Mapped[str] = mapped_column(Text, default="")
    # VER-030 修正稿重新跑一遍平台判据的结果
    criteria_results: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VerificationLesson(Base):
    """VER-040 核验经验。

    `KnowledgeCard` 记的是类目/城市/价格/工期——**记不下「怎么做才对」**。
    核验结论恰好是这个信息，而且是带标注的：
    输入（任务描述 + AI 产出）→ 人的判断（对 / 改成这样 / 错）→ 理由。

    脱敏与 KB-002 同规矩：不含个人信息、不含精确位置、不含金额细节。
    """

    __tablename__ = "verification_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    outcome: Mapped[str] = mapped_column(String(12))
    task_title: Mapped[str] = mapped_column(String(120), default="")
    # 判据文本列表（不含判据实现，实现是平台侧的）
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")
    revision_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
