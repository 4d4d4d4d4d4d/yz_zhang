"""COOP 早期合作体的数据模型（50 号 spec）。

核心与公司股权最本质的区别：**份额不是分的，是长出来的**。

传统公司先分股权再干活——分的那一刻谁干多少还不知道，干到一半有人不干了
股权还在他手里，早期合作最常死在这里。这里反过来：
`share_bps = 该成员已确认贡献计价 / 全体已确认贡献计价`。

所以 **`share_bps` 不是一个存储字段**，是算出来的。存下来就会漂——
有人新增贡献而没人回来重算，份额就是错的，而且不会有任何东西报错。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 贡献类型。计价由**确认人**给，不由贡献人给（COOP-010）。
CONTRIBUTION_KINDS = ("time", "money", "ip", "resource", "other")


class Venture(Base):
    """一个合作体 = 一行 User（is_venture=True）+ 一行 Venture。

    与 V73「agent 是 User」同一条理由：钱包、托管、合约、纠纷、任务发布
    全部以 user_id 为键。合作体要有资金池、要能发任务，不复用就得各写第二遍。
    """

    __tablename__ = "ventures"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(Text, default="")
    founder_id: Mapped[int] = mapped_column(Integer, index=True)
    # forming（组建中）/ active / closed
    status: Mapped[str] = mapped_column(String(12), default="forming", index=True)
    category: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VentureMember(Base):
    __tablename__ = "venture_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venture_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(12), default="member")   # founder / member
    # COOP-030 风险揭示书签署留痕。**不签不能加入**——一个不告诉人有风险
    # 就拉人进来的早期合作，本身就是纠纷的起点。
    risk_disclosure_version: Mapped[str] = mapped_column(String(20), default="")
    risk_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Contribution(Base):
    """COOP-010 贡献。提交后是 `proposed`，**必须由另一名成员确认**才计入份额。

    自报贡献等于自己发股份——「我说我干了 1000 小时」和 agent 自报置信度
    是同一类无效（AGT-030 的同一条道理）。
    """

    __tablename__ = "contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venture_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    # proposed / accepted / rejected
    status: Mapped[str] = mapped_column(String(12), default="proposed", index=True)
    # **计价由确认人给**：贡献人说「我做了什么」，确认人说「这值多少」。
    # 描述与估值分开，防止一个人既当运动员又当裁判。
    valued_cents: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirm_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Distribution(Base):
    """COOP-020 收益分配。**只分已实现的**——钱来自合作体钱包的可用余额。

    没有「预期收益」这个概念，代码里也不存在这个字段。这不是法务加的限制，
    是让这个模型落在合作内部分配、而不是涉众性金融的设计本身。
    """

    __tablename__ = "distributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venture_id: Mapped[int] = mapped_column(Integer, index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    # 分配那一刻的份额快照：份额是算出来的，但**分配依据必须留痕**，
    # 否则事后重算会得到不同的数字，对不上账
    share_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    memo: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
