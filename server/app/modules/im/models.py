from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # direct 单聊 / task 任务会话 / group 群聊（IM-003）
    kind: Mapped[str] = mapped_column(String(20), default="direct")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # 用户 id 列表
    # IM-052 单聊的「参与者对」规范化键（小 id-大 id），**唯一**。
    #
    # 为什么要这一列：`participants` 是 JSON，数据库没法在它上面建唯一约束，
    # 于是 `get_or_create_direct` 的 check-then-insert **没有任何东西兜底**——
    # 并发会建出两条单聊，两人各说各话、消息分在两条线上。
    # 探针实测：并发 10 次开同一个单聊，拿到两个会话 id。
    #
    # **没有约束的地方，竞态不报错，只把数据悄悄弄错**，比 500 难查得多
    # （V112 的钱包是同一个形状，但那张表有唯一约束，所以它只是 500）。
    #
    # 任务会话与群聊是 NULL：两个库都允许唯一列里有多个 NULL，
    # 所以这一列只约束它该约束的那一类。
    # `index=True, unique=True` 而不是只写 `unique=True`：后者在模型侧渲染成
    # UniqueConstraint，而迁移建的是**具名唯一索引**，两边对不上——
    # `alembic check` 当场报漂移（V109 的列属性闸门刻意不比索引名，
    # 所以那条测试看不见它，是 `alembic check` 抓到的）。
    direct_key: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True, unique=True)
    # IM-003 群聊元信息。放在同一张表而不是另起一张：成员资格就是
    # `participants`，发消息的鉴权（_get_conv）因此**自动**覆盖群聊——
    # 另起一张表就要再写一遍鉴权，而那正是「同一条规则两份实现」。
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    announcement: Mapped[str] = mapped_column(String(500), default="")
    muted: Mapped[list] = mapped_column(JSON, default=list)  # 被禁言的用户 id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    """任务会话消息即纠纷证据链的一部分（TASK-023），只增不删。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_id: Mapped[int] = mapped_column(Integer)
    # IM-009 消息类型：text 文本 / quote 报价卡（content 存结构化 JSON）
    kind: Mapped[str] = mapped_column(String(10), default="text")
    content: Mapped[str] = mapped_column(Text)
    # IM-006 风控：命中站外引导/联系方式模式时标记（提示防跳单，不拦截内容本身）
    risk_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    # IM-004 撤回：内容保留为审计副本（任务会话证据链要求），仅展示层隐藏
    recalled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConversationRead(Base):
    """IM-010 已读位点：每人每会话记录读到的最后一条消息 id，用于未读数与红点。"""

    __tablename__ = "conversation_reads"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
