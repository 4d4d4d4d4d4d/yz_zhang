from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Report(Base):
    """RISK-007 举报中心：全对象可举报，进入人审队列（RISK-002）。"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(Integer, index=True)
    target_type: Mapped[str] = mapped_column(String(20))  # task/content/user/message
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/resolved
    action: Mapped[str] = mapped_column(String(20), default="")  # dismiss/remove_content/ban_user
    handled_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminAudit(Base):
    """OPS-012 管理员操作审计：高权限动作（封禁/裁决/结算等）不可抵赖留痕。

    只增不改，记录 谁(admin_id) 在何时 对什么对象(target) 做了什么(action)。
    """

    __tablename__ = "admin_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)  # ban_user/dispute_verdict/...
    target_type: Mapped[str] = mapped_column(String(20), default="")
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # ADMIN-062 哈希链（149 号 spec）：本条的哈希 = sha256(上一条的哈希 + 本条内容)。
    # 改一条、删中间一条、删最后几条，自检都能指出在哪里断的。V177 之前的旧记录没有哈希，不在链上
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="", index=True)


class AuditChainHead(Base):
    """ADMIN-062 链头（只有一行）：最新一条的编号与哈希。写审计时锁住它，并发写也排成一条链；
    删掉最后几条时，链头对不上就能发现。"""
    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_audit_id: Mapped[int] = mapped_column(Integer, default=0)
    last_hash: Mapped[str] = mapped_column(String(64), default="")
    count: Mapped[int] = mapped_column(Integer, default=0)


class QueueSlaNotice(Base):
    """QUEUE-012 超时告知过谁（78 号 spec）。

    「已经告知过提交方」这个状态要存在**队列之外**：六个队列分别落在六张表里，
    给每张表加一个 `sla_notified_at` 是六次迁移、六处容易漏的地方。
    这里一行记一件，`item_key` 用字符串——上传队列的主键是文件名，不是整数。

    只增不改：每件只告知一次，否则每小时一条通知比不发更糟。
    """

    __tablename__ = "queue_sla_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_key: Mapped[str] = mapped_column(String(24), index=True)
    item_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Announcement(Base):
    """NTF-064 全站公告的记录（151 号 spec）：预览之后发、可以定时、发错了可以撤回。

    此前公告只是一个循环：发给谁、什么时候、多少人收到，事后都查不到；发错了只能再发一条更正。"""
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(2000), default="")
    verified_only: Mapped[bool] = mapped_column(Boolean, default=False)
    # NTF-066（159 号 spec）定向：城市（空 = 不限）与人群（all / publishers 近 180 天发过单 / workers 近 180 天报过名）
    city: Mapped[str] = mapped_column(String(50), default="")
    audience: Mapped[str] = mapped_column(String(12), default="all")
    # scheduled（等时间到）/ sent / cancelled（定时的取消了，没发）/ revoked（发了又撤回）
    status: Mapped[str] = mapped_column(String(12), default="sent", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
    closed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str] = mapped_column(String(200), default="")


class PlatformSettleRequest(Base):
    """SEC-061c / PAY-042b 大额平台结算的四眼（148 号 spec）：一位财务发起，另一位财务确认后才真的划出。"""
    __tablename__ = "platform_settle_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    memo: Mapped[str] = mapped_column(String(200), default="")
    requested_by: Mapped[int] = mapped_column(Integer, index=True)
    # awaiting_second / settled / rejected
    status: Mapped[str] = mapped_column(String(16), default="awaiting_second", index=True)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
