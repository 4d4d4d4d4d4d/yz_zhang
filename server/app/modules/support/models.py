from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Ticket(Base):
    """CS-013 工单：AI 无法解决时转人工跟进。"""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open/resolved/escalated
    # ESCA-001 转纠纷后两边互相能找到。不留这个指针，用户在工单里说过的话
    # 就和纠纷失联了，而他会被迫再说一遍——两次陈述不一致会被当成翻供。
    escalated_to_dispute_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply: Mapped[str] = mapped_column(Text, default="")
    handler_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ESCA-051 认领与超时升级（150 号 spec）：谁接手了；升到第几级（0 未升级 / 1 叫醒客服 / 2 叫醒主管）。
    # 级别本身就是去重：每一级只叫一次人
    assignee_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    # ESCA-052（172 号 spec）提单人选的类别（funds 资金 / account 账号 / general 一般）与优先级（urgent / normal）。
    # 资金、账号类默认加急，时限更短；客服可以调整优先级
    category: Mapped[str] = mapped_column(String(10), default="general")
    # ESCA-057（227 号 spec）提单时附的截图：自己上传过的图片名（最多 4 张）
    images: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ESCA-053 首次响应（157 号 spec）：客服第一次回话的时间；超时提醒只发一次
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_response_alerted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TicketReply(Base):
    """ESCA-053 工单里的往来（157 号 spec）：客服可以先回一句、不结单；结单时的回复也记一条。
    `Ticket.reply` 仍是最近一次客服回复（兼容原有字段）。"""
    __tablename__ = "ticket_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, index=True)
    author_id: Mapped[int] = mapped_column(Integer)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=True)
    body: Mapped[str] = mapped_column(Text)
    # ESCA-057 追加回复时附的截图
    images: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotificationPref(Base):
    """NTF-003 通知偏好：按分类开关。"""

    __tablename__ = "notification_prefs"
    __table_args__ = (UniqueConstraint("user_id", "category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(20))  # task/funds/system
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SupportAgentScope(Base):
    """ESCA-061（234 号 spec）客服自己声明负责哪几类工单（funds / account / general）。
    没声明的客服视为什么都管；没人接手的工单超时提醒优先叫负责这一类的人。"""

    __tablename__ = "support_agent_scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # ESCA-064（237 号 spec）新工单自动分给我（按负责的类别、手上未结的最少的人先分）；默认不分
    auto_assign: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    # ESCA-065（240 号 spec）暂停接单到这个时间（下班 / 请假）：自动分配跳过、超时提醒先叫别人；过了自动恢复
    paused_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ESCA-068（260 号 spec）排班：[{weekday 0~6（周一为 0）, start "09:00", end "18:00"}]，北京时间；
    # 设了排班的人在排班以外的时间算「不在岗」（与暂停同样处理）；不设 = 一直在岗（与以前一样）
    schedule: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
