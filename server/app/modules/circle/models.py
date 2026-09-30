from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

CIRCLE_KINDS = ["interest", "skill", "local"]  # CIR-001 兴趣圈/能力圈/地域圈
JOIN_POLICIES = ["open", "approval"]  # 公开加入 / 申请审核（invite 制 V2）


class Circle(Base):
    __tablename__ = "circles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(12), default="interest")
    join_policy: Mapped[str] = mapped_column(String(12), default="open")
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    # 能力圈绑定技能标签（CIR-003 门槛匹配）；地域圈绑定城市
    skill_tag: Mapped[str] = mapped_column(String(50), default="")
    city: Mapped[str] = mapped_column(String(50), default="")
    # CIR-003 能力圈门槛：最低信用分
    min_credit: Mapped[int] = mapped_column(Integer, default=0)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # CIR-006 圈层群聊
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CircleMember(Base):
    __tablename__ = "circle_members"
    __table_args__ = (UniqueConstraint("circle_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circle_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")  # owner/admin/member
    status: Mapped[str] = mapped_column(String(10), default="active")  # active/pending
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
