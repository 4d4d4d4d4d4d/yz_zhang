"""SBX-106 端侧模型目录（128 号 spec）：平台审核过、可以下载到手机上跑的量化小模型。

模型文件不经平台服务器：手机直接从登记的地址下载，下载完按登记的 sha256 校验，对不上就删掉不用。
登记与上架走四眼：写的人不能自己上架，上架时必须有 sha256、https 地址与大小。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class SandboxModel(Base):
    __tablename__ = "sandbox_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    family: Mapped[str] = mapped_column(String(60), default="")
    params_b: Mapped[float] = mapped_column(Float, default=0.0)        # 参数量（十亿）
    quant: Mapped[str] = mapped_column(String(20), default="")         # 量化方式，例如 Q4_K_M
    file_format: Mapped[str] = mapped_column(String(20), default="gguf")
    size_mb: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    license: Mapped[str] = mapped_column(String(100), default="")
    min_ram_gb: Mapped[float] = mapped_column(Float, default=0.0)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)           # 适合的本机技能：summarize / checklist / …
    note: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)   # draft / published / retired
    created_by: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retired_reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
