"""SKL-101 技能概念表（135 号 spec）：运营在后台增改的概念（覆盖或补充仓库里的种子）。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class SkillConcept(Base):
    __tablename__ = "skill_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)       # 规范名
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="active")   # active / retired（下线后种子里的同名概念也不再生效）
    updated_by: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
