from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="direct")  # direct 单聊 / task 任务会话
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # 用户 id 列表
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    """任务会话消息即纠纷证据链的一部分（TASK-023），只增不删。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # IM-006 风控：命中站外引导/联系方式模式时标记（提示防跳单，不拦截内容本身）
    risk_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    # IM-004 撤回：内容保留为审计副本（任务会话证据链要求），仅展示层隐藏
    recalled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
