"""TEAM 团队账户（53 号 spec）。

架构判断第三次用同一条（V73 agent、V75 合作体、这里）：**团队也是一行 User**。
钱包、托管、合约、纠纷、发任务全部以 `user_id` 为键，团队要有公共资金池、
要以团队名义发任务、要被开票，不复用就得各写第二遍。

**与合作体的区别**（不说清楚两者会混）：
合作体是**分钱**的（贡献即份额，按份额分配收益），团队是**花钱**的
（公司充值，按角色与额度支出，不分配）。两者都要资金池但规则相反，
所以是两个模块，而不是一个带开关的模块。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# TEAM-010 **刻意不做通用 RBAC**：一个可配置的权限矩阵在这个阶段只会让人配错。
# 三档覆盖绝大多数团队，且每一档「能做什么」一句话说得清。
ROLES = ("owner", "admin", "member")


class Team(Base):
    __tablename__ = "teams"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    owner_id: Mapped[int] = mapped_column(Integer, index=True)

    # TEAM-030 企业信息。**没核过不能开票**——一张开给未核验抬头的发票，
    # 是税务风险不是便利。
    company_name: Mapped[str] = mapped_column(String(120), default="")
    tax_number: Mapped[str] = mapped_column(String(40), default="")
    license_images: Mapped[str] = mapped_column(Text, default="")   # 逗号分隔的文件名
    # none / pending / verified / rejected
    verify_status: Mapped[str] = mapped_column(String(12), default="none", index=True)
    verify_reason: Mapped[str] = mapped_column(Text, default="")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")
    # TEAM-011 **单笔**额度，不是月度池。
    # 月度池要处理周期、结转、跨月退款归属，复杂度高一个数量级，
    # 而它解决的主要问题（防一个人把钱花光）单笔额度也能解决大半。
    spend_limit_cents: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SpendRequest(Base):
    """TEAM-020 超额支出审批单。

    **审批期间不预扣团队资金**：预扣会让一堆待批的申请把预算占死，
    而审批本来就可能被驳回。代价是批准时可能余额不足——那时明确报错，
    比钱被占住好。
    """

    __tablename__ = "team_spend_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(200), default="")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # pending / approved / rejected / executed
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
