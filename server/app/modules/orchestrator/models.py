"""ORC 编排循环（Agent Harness）：把「发任务给人」当作工具调用来编排。

心智模型对齐 agent harness：
  Mission(目标) ≈ 一次 agent run；MissionStep(一步) ≈ 一次 tool call，
  而 tool 的实现体就是本平台的「发布任务 → 合约托管 → 他人执行 → 验收」。
Loop：plan（规划下一步）→ dispatch（发任务=调用工具）→ observe（验收/校验产出）
      → evaluate（完成度与问题）→ 若有问题则生成修复步再分发，直至达标或触及护栏。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

MISSION_STATUSES = ("planning", "running", "blocked", "succeeded", "failed", "cancelled")

# 编排状态机（与任务状态机同一治理原则：白名单流转）
MISSION_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"running", "cancelled", "failed"},
    "running": {"blocked", "succeeded", "failed", "cancelled"},
    "blocked": {"running", "cancelled", "failed"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}


class Mission(Base):
    """ORC-001 编排目标：一次「人类工具」的 agent run。"""

    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    goal: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="跑腿")
    status: Mapped[str] = mapped_column(String(12), default="planning")
    # ORC-004 护栏：预算上限与迭代上限，防 runaway agent 烧钱/死循环
    budget_cap_cents: Mapped[int] = mapped_column(Integer, default=0)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)  # 已分发（已承诺）预算
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    completion_pct: Mapped[int] = mapped_column(Integer, default=0)  # 0~100
    # ORC-005 验收标准：每步产出按此校验（人工验收 + 规则校验的依据）
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    last_error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MissionStep(Base):
    """ORC-002 一步 = 一次工具调用；tool=publish_task 时对应一个真实任务与合约。"""

    __tablename__ = "mission_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(Integer, index=True)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    tool: Mapped[str] = mapped_column(String(30), default="publish_task")
    title: Mapped[str] = mapped_column(String(120))
    args: Mapped[dict] = mapped_column(JSON, default=dict)  # 工具入参（任务规格）
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # pending 待分发 / dispatched 已发任务 / done 已验收 / failed 未通过或取消
    status: Mapped[str] = mapped_column(String(12), default="pending")
    observation: Mapped[str] = mapped_column(Text, default="")  # 观测结果（成果/问题）
    is_remedy: Mapped[bool] = mapped_column(Integer, default=0)  # 是否为修复步（迭代产物）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
