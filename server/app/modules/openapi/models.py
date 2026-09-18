"""API / HOOK 开放接口与 Webhook（54 号 spec）。

现状实测：全站唯一的身份是**用户会话 token**（绑 `sid`，改密即全端下线）。
那是给**人**用的。最省事的做法是「让集成方存一个用户 token」，三条都不成立：

1. 用户改一次密码，对方的集成第二天就全挂了，而且不知道为什么；
2. 会话 token 能提现、能改密、能注销账号——集成方只想读任务列表，
   凭什么给他一把能把钱转走的钥匙；
3. 出问题时分不清是本人操作还是集成方调的。

所以 API Key 是**另一类主体**，不是用户凭证的别名。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# API-002 Scope 白名单。**没有 wallet:write，也没有任何提现相关的 scope。**
#
# 出金是这个平台上唯一不可逆的动作。集成方的 key 泄露概率远高于用户密码
# （它躺在 CI 变量、日志、截图里），而一次错误出金是追不回来的。
# 需要程序化出金的场景，等有真实需求、且能配上白名单收款账户与二次确认再说。
SCOPES = (
    "tasks:read",
    "tasks:write",
    "wallet:read",
    "webhooks:manage",
)

SCOPE_LABELS = {
    "tasks:read": "读取任务",
    "tasks:write": "发布与编辑任务",
    "wallet:read": "读取余额与流水",
    "webhooks:manage": "管理自己的 Webhook",
}

# HOOK-051 开放的事件类型。**不是全量**——开放一个没审过的事件体
# （里面可能带手机号、地址、金额）比不开放更危险。
WEBHOOK_EVENTS = (
    "task.published",
    "task.matched",
    "task.delivered",
    "task.completed",
    "task.cancelled",
    "contract.funded",
    "contract.released",
    "dispute.opened",
)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60), default="")
    # API-001 **只存哈希**。与密码同一条道理：能解出来就意味着有人能解出来。
    # 找回的便利，不值得拿「库被拖走时所有集成方的凭证同时泄露」去换。
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 给用户认出是哪一把（前 8 位），不足以用来调用
    key_prefix: Mapped[str] = mapped_column(String(16), default="")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    url: Mapped[str] = mapped_column(String(500))
    events: Mapped[list] = mapped_column(JSON, default=list)
    # HOOK-001 **每个 webhook 独立的 secret**，不是全局的——
    # 一个泄露不该让所有人的签名都可伪造
    secret: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    disabled_reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WebhookDelivery(Base):
    """HOOK-002 每次投递留记录。

    没有记录的话，集成方报「我没收到」时平台只能说「我发了」——
    两边都无法证明，这种争执没有出口。
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending / delivered / failed / dead
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_code: Mapped[int] = mapped_column(Integer, default=0)
    response_excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
