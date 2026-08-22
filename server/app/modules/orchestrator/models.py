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
    # AIO-024 预算拆成两个量，各司其职（原实现把两者混为一谈，见 24 号 spec）：
    #   committed = 当前占用额度：分发时 +，任务取消/流单（钱没花出去）时 −
    #   spent     = 真实花费：任务完成放款时才 +，可与钱包账本交叉核对
    # 混在一起的后果是「取消的任务永久占着额度」，几轮迭代后 agent 必然饿死
    committed_cents: Mapped[int] = mapped_column(Integer, default=0)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    completion_pct: Mapped[int] = mapped_column(Integer, default=0)  # 0~100 步骤完成率
    # AIO-020 质量维度：已完成步的平均评审分。达标要求「全部完成」且「均分过线」
    quality_pct: Mapped[int] = mapped_column(Integer, default=0)
    # AIO-034 模型调用配额：达上限即降级规则评审，不静默烧 API 账单
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
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
    # AIO-022 修复步幂等改用外键，不再靠标题字符串匹配（原实现多轮后标题会
    # 变成「[修复] [修复] [修复] X」，且匹配本身很脆）
    parent_step_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)  # 第几次尝试（标题保持稳定）
    # AIO-001 本步的验收要点（下发给执行者，也是评审的判据）
    acceptance: Mapped[list] = mapped_column(JSON, default=list)
    # AIO-010~013 评审结果：verdict pass/revise/fail，score 0-100
    review_verdict: Mapped[str] = mapped_column(String(10), default="")
    review_score: Mapped[int] = mapped_column(Integer, default=0)
    review_missing: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MissionEvent(Base):
    """AIO-023 迭代时间线：每轮 tick 的人类可读摘要。

    agent 必须可解释，否则没人敢授权它自动花钱——「做了什么 / 卡在哪 / 下一步」
    要能一眼看懂，而不是只留下一堆状态字段。
    """

    __tablename__ = "mission_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(Integer, index=True)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(20), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StepReview(Base):
    """AIO-013 评审留痕：没有留痕的自动判定在纠纷里毫无价值。"""

    __tablename__ = "step_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(Integer, index=True)
    reviewer: Mapped[str] = mapped_column(String(40), default="rule")  # rule / anthropic:<model>
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    verdict: Mapped[str] = mapped_column(String(10), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    input_digest: Mapped[str] = mapped_column(String(400), default="")  # 脱敏摘要
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
