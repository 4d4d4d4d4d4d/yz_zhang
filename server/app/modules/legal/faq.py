"""LAW-060 法律常识库的运营草稿流（163 号 spec，V192，SCN-114）。

代码里的 `LEGAL_FAQS` 是最早的四条，不动（只增不减）；运营补的条目进 `legal_faqs` 表：
草稿 → 提交审核 → 另一位合规管理员上线 → 可下线（写理由）。法律问答同时查两处，上线的条目带出处。

雷达上「法律问答答不上」的主题可以一键起草：关键词取主题表里的常见词，回答与出处留「【待填写】」，
不填完不能提交、不能上线——法律内容不能由模板或模型代写结论。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.admin_roles import require_role
from app.core.db import Base, get_db
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow
from app.modules.packs.schema import PLACEHOLDER

STATUSES = ("draft", "review", "published", "retired")


class LegalFaq(Base):
    __tablename__ = "legal_faqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(20), default="", index=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    answer: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)
    origin: Mapped[str] = mapped_column(String(60), default="")      # radar:legal_gap:<主题> / manual
    created_by: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def published(db: Session) -> list[LegalFaq]:
    return db.query(LegalFaq).filter(LegalFaq.status == "published").order_by(LegalFaq.id).all()


def placeholders_left(f: LegalFaq) -> list[str]:
    return [name for name, v in (("回答", f.answer), ("出处", f.source)) if PLACEHOLDER in (v or "")]


def dump(f: LegalFaq) -> dict:
    return {"id": f.id, "topic": f.topic, "keywords": list(f.keywords or []), "answer": f.answer, "source": f.source,
            "status": f.status, "origin": f.origin, "created_by": f.created_by, "reviewed_by": f.reviewed_by,
            "published_at": iso(f.published_at), "retired_reason": f.retired_reason,
            "placeholders": placeholders_left(f), "updated_at": iso(f.updated_at)}


# ------------------------------------------------------------------ 接口（合规管理员）
router = APIRouter(tags=["legal"])
ROLE = "compliance"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaqIn(_In):
    topic: str = Field(default="", max_length=20)
    keywords: list[str] = Field(min_length=1, max_length=20)
    answer: str = Field(min_length=10, max_length=3000)
    source: str = Field(min_length=2, max_length=300)


class RadarFaqIn(_In):
    topic: str = Field(min_length=1, max_length=20)


class RetireIn(_In):
    reason: str = Field(min_length=2, max_length=300)


def _clean_keywords(words: list[str]) -> list[str]:
    out = []
    for w in words:
        w = w.strip()
        if w and w not in out:
            out.append(w[:20])
    if not out:
        raise bad_request("至少写一个关键词：用户的问题里出现它才会匹配到这一条", "legal_faq_no_keywords")
    return out


def _own(db: Session, faq_id: int) -> LegalFaq:
    f = db.get(LegalFaq, faq_id)
    if f is None:
        raise not_found("没有这条法律知识")
    return f


def _no_placeholders(f: LegalFaq) -> None:
    left = placeholders_left(f)
    if left:
        raise conflict(f"{'、'.join(left)}里还有「{PLACEHOLDER}」没填：写完再提交", "pack_placeholder_left")


@router.get("/admin/legal/faqs")
def list_faqs(admin: User = Depends(require_role(ROLE)), db: Session = Depends(get_db, scope="function")):
    return [dump(f) for f in db.query(LegalFaq).order_by(LegalFaq.id.desc()).limit(200).all()]


@router.post("/admin/legal/faqs", status_code=201)
def create_faq(body: FaqIn, admin: User = Depends(require_role(ROLE)), db: Session = Depends(get_db, scope="function")):
    now = utcnow()
    f = LegalFaq(topic=body.topic.strip(), keywords=_clean_keywords(body.keywords), answer=body.answer.strip(),
                 source=body.source.strip(), status="draft", origin="manual", created_by=admin.id,
                 created_at=now, updated_at=now)
    db.add(f)
    db.flush()
    return dump(f)


@router.put("/admin/legal/faqs/{faq_id}")
def update_faq(faq_id: int, body: FaqIn, admin: User = Depends(require_role(ROLE)),
               db: Session = Depends(get_db, scope="function")):
    f = _own(db, faq_id)
    if f.status != "draft":
        raise conflict("只有草稿能改：已上线的要改，先下线再起一条新的", "legal_faq_not_draft")
    f.topic, f.keywords = body.topic.strip(), _clean_keywords(body.keywords)
    f.answer, f.source, f.updated_at = body.answer.strip(), body.source.strip(), utcnow()
    db.add(f)
    db.flush()
    return dump(f)


@router.post("/admin/legal/faqs/radar-draft", status_code=201)
def radar_draft(body: RadarFaqIn, admin: User = Depends(require_role(ROLE)),
                db: Session = Depends(get_db, scope="function")):
    """SCN-114 雷达上「法律问答答不上」的主题 → 一条法律知识草稿。只认雷达此刻真有的主题（至少 3 个不同的人）。"""
    from app.modules.admin.router import record_audit
    from app.modules.packs import service as packs
    from app.modules.packs.topics import LEGAL_TOPICS

    signal = next((x for x in packs.radar(db) if x["source"] == "legal_gap" and x["key"] == body.topic), None)
    if signal is None:
        raise not_found("雷达上没有这个法律主题了（人数不够或已经不再出现）：刷新雷达再选")
    words = list(LEGAL_TOPICS.get(body.topic, ()))
    if not words:
        raise conflict("这个主题没有常见词（例如「其他」），起草出来匹配不到任何问题：请手写关键词新建", "legal_faq_no_keywords")
    now = utcnow()
    f = LegalFaq(topic=body.topic, keywords=words,
                 answer=(f"{PLACEHOLDER}这里写给用户看的回答：先说结论，再说依据和步骤；拿不准的写明「建议找律师」。\n\n"
                         f"起草依据（场景雷达）：{signal['evidence']}"),
                 source=f"{PLACEHOLDER}出处：法规名与条号（例如《民法典》第几条）或官方链接",
                 status="draft", origin=f"radar:legal_gap:{body.topic}"[:60], created_by=admin.id,
                 created_at=now, updated_at=now)
    db.add(f)
    db.flush()
    record_audit(db, admin.id, "legal_faq_radar_draft", "legal_faq", f.id, f"{body.topic}（{signal['people']} 人）")
    return dump(f)


@router.post("/admin/legal/faqs/{faq_id}/submit")
def submit_faq(faq_id: int, admin: User = Depends(require_role(ROLE)), db: Session = Depends(get_db, scope="function")):
    f = _own(db, faq_id)
    if f.status != "draft":
        raise conflict("只有草稿能提交审核", "legal_faq_not_draft")
    _no_placeholders(f)
    f.status, f.updated_at = "review", utcnow()
    db.add(f)
    db.flush()
    return dump(f)


@router.post("/admin/legal/faqs/{faq_id}/approve")
def approve_faq(faq_id: int, admin: User = Depends(require_role(ROLE)), db: Session = Depends(get_db, scope="function")):
    """四眼：写它的人不能自己批。上线后法律问答立刻能用它回答，并带出处。"""
    from app.modules.admin.router import record_audit

    f = _own(db, faq_id)
    if f.status != "review":
        raise conflict("只有待审核的能上线", "legal_faq_not_in_review")
    if f.created_by == admin.id:
        raise conflict("上线需要另一位合规管理员审核：写它的人不能自己批", "legal_faq_four_eyes")
    _no_placeholders(f)
    f.status, f.reviewed_by, f.published_at, f.updated_at = "published", admin.id, utcnow(), utcnow()
    db.add(f)
    record_audit(db, admin.id, "legal_faq_publish", "legal_faq", f.id, f"{f.topic} {'、'.join(f.keywords[:5])}")
    db.flush()
    return dump(f)


@router.post("/admin/legal/faqs/{faq_id}/reject")
def reject_faq(faq_id: int, admin: User = Depends(require_role(ROLE)), db: Session = Depends(get_db, scope="function")):
    f = _own(db, faq_id)
    if f.status != "review":
        raise conflict("只有待审核的能退回", "legal_faq_not_in_review")
    f.status, f.updated_at = "draft", utcnow()
    db.add(f)
    db.flush()
    return dump(f)


@router.post("/admin/legal/faqs/{faq_id}/retire")
def retire_faq(faq_id: int, body: RetireIn, admin: User = Depends(require_role(ROLE)),
               db: Session = Depends(get_db, scope="function")):
    """下线要写理由（法规变了、写错了）；记录留着，问答立刻不再用它。"""
    from app.modules.admin.router import record_audit

    f = _own(db, faq_id)
    if f.status == "retired":
        raise conflict("已经下线了", "legal_faq_retired")
    f.status, f.retired_reason, f.updated_at = "retired", body.reason.strip(), utcnow()
    db.add(f)
    record_audit(db, admin.id, "legal_faq_retire", "legal_faq", f.id, body.reason.strip())
    db.flush()
    return dump(f)
