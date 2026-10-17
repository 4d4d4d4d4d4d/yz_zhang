"""GIG-100 接单者服务包（125 号 spec）：现在有空、常用地点、附近推单、顺路单、报价参考。

位置是敏感个人信息：只存**粗化到约 1 公里**的坐标；「现在有空」到点自动失效，关掉就删。
"""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class GigAvailability(Base):
    __tablename__ = "gig_availability"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    until: Mapped[datetime] = mapped_column(DateTime, index=True)
    lat: Mapped[float] = mapped_column(Float)          # 粗化到 0.01 度（约 1 公里）
    lng: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[int] = mapped_column(Integer, default=5)
    categories: Mapped[list] = mapped_column(JSON, default=list)   # 空 = 都可以
    pushed: Mapped[int] = mapped_column(Integer, default=0)        # 这一段「有空」里推了几条（有上限）
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GigPlace(Base):
    """常用地点（家、公司、常去的商圈）：顺路单的起点与终点。同样只存粗化坐标。"""
    __tablename__ = "gig_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(20))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GigRoute(Base):
    """SCN-140（208 号 spec）常用路线：哪几天、几点从哪个常用地点出发去哪个。到点前推顺路的名额。
    不存坐标（坐标在常用地点上，已粗化）；地点删了，用到它的路线一起删。"""
    __tablename__ = "gig_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    from_place_id: Mapped[int] = mapped_column(Integer)
    to_place_id: Mapped[int] = mapped_column(Integer)
    weekdays: Mapped[list] = mapped_column(JSON, default=list)     # 0 = 星期一（北京时间）
    depart_hm: Mapped[str] = mapped_column(String(5))              # 北京时间 HH:MM
    within_hours: Mapped[int] = mapped_column(Integer, default=3)
    last_pushed_on: Mapped[date | None] = mapped_column(Date, nullable=True)   # 一天最多推一次
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
