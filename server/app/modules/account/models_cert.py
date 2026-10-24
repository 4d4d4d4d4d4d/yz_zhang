"""CERT 职业资质申请与核验（51 号 spec）。

改造前 `POST /users/me/certifications` 的实现是一行
`user.certifications += [name]`，注释写着「模拟审核即通过」——
**任何实名用户 POST 一个字符串就能拿到「电工」资质**，
而 `task/service.py` 正是用这个字段拦住电工维修、燃气维修、法律咨询的接单。

一个无证的人接了电工单，出事的是人身安全，赔的是平台的连带责任。
所以这一批的完成定义不是「加了个审核页面」，而是
**在资质被人工核过之前，那个类目的接单准入一次都不放行**。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# pending 待审 / approved 已核准 / rejected 驳回 / revoked 已撤销
CERT_STATUSES = ("pending", "approved", "rejected", "revoked")


class CertificationApplication(Base):
    __tablename__ = "certification_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(30), index=True)      # 「电工」「律师」…

    # CERT-003 证件上的姓名。**这条最容易漏，漏了前面几条全白做**——
    # 一张别人的电工证也是一张真证件。服务端与 user.real_name 严格比对。
    holder_name: Mapped[str] = mapped_column(String(50), default="")
    cert_number: Mapped[str] = mapped_column(String(60), default="")
    issuer: Mapped[str] = mapped_column(String(80), default="")
    # CERT-005 有效期。**「发了就永久有效」是错的**，而且是几年后才会伤到人的错。
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # CERT-002 证件影像（UploadedFile.name 列表）。没有影像，审核员看什么？
    images: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    # 驳回必须带理由——只说「未通过」，申请人不知道该补什么，只会一遍遍重交
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
