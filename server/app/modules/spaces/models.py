from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class PersonalSpace(Base):
    __tablename__ = 'personal_spaces'
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    headline: Mapped[str] = mapped_column(String(120), default='')
    introduction: Mapped[str] = mapped_column(String(1600), default='')
    theme: Mapped[str] = mapped_column(String(20), default='clay')
    items: Mapped[list] = mapped_column(JSON, default=list)
