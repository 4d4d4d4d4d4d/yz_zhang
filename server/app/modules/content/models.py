from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

CONTENT_KINDS = ["post", "blog", "case"]  # 动态 / 博客长文 / 任务案例卡
VISIBILITIES = ["public", "followers", "circle", "private"]  # CNT-001 可见性


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10), default="post")
    title: Mapped[str] = mapped_column(String(120), default="")  # blog/case 用
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)  # CNT-004 与技能标签同体系
    visibility: Mapped[str] = mapped_column(String(12), default="public")
    circle_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # CNT-012 圈层内容
    # CNT-005 挂载服务入口：内容页可直达"找我做同款"
    linked_category: Mapped[str] = mapped_column(String(50), default="")
    source_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # case 卡来源
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="published")  # published/removed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Follow(Base):
    """CNT-021 关注关系。"""

    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    follower_id: Mapped[int] = mapped_column(Integer, index=True)
    followee_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "content_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    content_id: Mapped[int] = mapped_column(Integer, index=True)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(Integer, index=True)
    author_id: Mapped[int] = mapped_column(Integer)
    reply_to_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 二级回复
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
