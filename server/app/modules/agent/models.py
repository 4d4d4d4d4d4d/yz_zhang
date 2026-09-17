"""AGT 平台自有 Agent 的数据模型（48 号 spec）。

架构判断见 spec 第 0 节：**一个 agent = 一行 `User`（`is_agent=True`）
+ 一行 `AgentProfile`**。

不做平行实体的理由不是省事——托管、纠纷、信用、账本、风控**全部以
`user_id` 为键**。做成平行实体等于把它们各写第二遍，而第二遍必然抄漏。
这正是 V58 修过的形状：同一个动作两条路，最常走的那条抄了近道。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class AgentProfile(Base):
    """平台自有 agent 的配置。owner 恒为平台，所以没有 owner 字段。"""

    __tablename__ = "agent_profiles"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # AGT-011 领域：task.category 必须命中其一
    domains: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(60), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")

    # AGT-016 平台买 API 的单次估算成本。**不允许为空**：
    # 没有这个数字，「让 agent 接单」到底是赚是赔谁也说不清
    cost_per_run_cents: Mapped[int] = mapped_column(Integer, default=0)
    # AGT-012 赔付能力上限：搞砸 200 元的文案认栽，搞砸 5 万的项目不行
    max_task_budget_cents: Mapped[int] = mapped_column(Integer, default=50000)
    # AGT-013 置信度阈值（万分比）
    confidence_threshold_bps: Mapped[int] = mapped_column(Integer, default=7000)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    runs_total: Mapped[int] = mapped_column(Integer, default=0)
    runs_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    runs_escalated: Mapped[int] = mapped_column(Integer, default=0)
    runs_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentRun(Base):
    """一次执行。成功与失败都落库——AGT-015 失败不假装成功，也不悄悄消失。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_user_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    contract_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # running / succeeded / escalated / failed
    status: Mapped[str] = mapped_column(String(12), default="running", index=True)
    # AGT-013 agent **自报**的置信度。正因为是自报，才需要 AGT-030 的
    # 客观判据压在它上面——自己声明「我很有信心」和自己声明「我通过了验收」
    # 是同一种无效。
    confidence_bps: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[str] = mapped_column(Text, default="")
    # AGT-030 逐条判据结果：[{"text":..., "kind":"auto", "passed":bool, "detail":...}]
    criteria_results: Mapped[list] = mapped_column(JSON, default=list)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
