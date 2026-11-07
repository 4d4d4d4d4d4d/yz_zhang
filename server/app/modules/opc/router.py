"""OPC-100 一人公司工具接口（124 号 spec）。全部只对本人；别人的 id 一律 404。"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import day, iso
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import OpcEntry, OpcProfile

router = APIRouter(tags=["opc"])
LIMIT_ENTRIES = 20000


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileIn(_In):
    entity: Literal["individual", "sole_prop", "company"]
    vat: Literal["none", "small_scale", "general"]
    vat_period: Literal["month", "quarter"] = "quarter"
    small_low_profit: bool = True


class EntryIn(_In):
    occurred_on: date
    kind: Literal["income", "expense"]
    amount_cents: int = Field(gt=0, le=10_000_000_000)
    tax_cents: int = Field(default=0, ge=0, le=10_000_000_000)
    category: str = Field(default="", max_length=20)
    counterparty: str = Field(default="", max_length=60)
    invoice_no: str = Field(default="", max_length=40)
    invoice_kind: Literal["none", "ordinary", "special"] = "none"
    note: str = Field(default="", max_length=200)


class EntryPatch(_In):
    occurred_on: date | None = None
    amount_cents: int | None = Field(default=None, gt=0, le=10_000_000_000)
    tax_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)
    category: str | None = Field(default=None, max_length=20)
    counterparty: str | None = Field(default=None, max_length=60)
    invoice_no: str | None = Field(default=None, max_length=40)
    invoice_kind: Literal["none", "ordinary", "special"] | None = None
    note: str | None = Field(default=None, max_length=200)


class ImportIn(_In):
    since: date | None = None


class ReviewIn(_In):
    text: str = Field(min_length=20, max_length=20000)
    role: Literal["party_a", "party_b", "unknown"] = "unknown"


def _today() -> date:
    """北京时间的今天：申报截止按当地日期算，UTC 的日期在零点到八点之间差一天。"""
    from app.modules.workbench.service import local

    return local(utcnow()).date()


def _profile(db: Session, user: User) -> OpcProfile | None:
    return db.get(OpcProfile, user.id)


def _dump_profile(p: OpcProfile | None, user_id: int) -> dict:
    p = p or OpcProfile(user_id=user_id, entity="individual", vat="none", vat_period="quarter", small_low_profit=True)
    return {"entity": p.entity, "vat": p.vat, "vat_period": p.vat_period, "small_low_profit": p.small_low_profit,
            "configured": p.updated_at is not None}


def _dump(e: OpcEntry) -> dict:
    return {"id": e.id, "occurred_on": day(e.occurred_on), "kind": e.kind, "amount_cents": e.amount_cents,
            "tax_cents": e.tax_cents, "category": e.category, "counterparty": e.counterparty,
            "invoice_no": e.invoice_no, "invoice_kind": e.invoice_kind, "note": e.note, "source": e.source,
            "created_at": iso(e.created_at)}


def _period(period: str) -> str:
    try:
        svc.parse_period(period)
    except ValueError:
        raise bad_request("期间写成 2026-10（月）、2026-Q3（季）或 2026（年）", "opc_bad_period") from None
    return period


def _own(db: Session, entry_id: int, user: User) -> OpcEntry:
    e = db.get(OpcEntry, entry_id)
    if e is None or e.owner_id != user.id:
        raise not_found("这条账不存在")
    return e


# ------------------------------------------------------------------ 主体设置
@router.get("/opc/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return _dump_profile(_profile(db, user), user.id)


@router.put("/opc/profile")
def put_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    if body.entity == "individual" and body.vat != "none":
        raise bad_request("没有登记主体的个人不是增值税纳税人：先选个体工商户或公司", "opc_profile_mismatch")
    p = _profile(db, user) or OpcProfile(user_id=user.id)
    p.entity, p.vat, p.vat_period, p.small_low_profit = body.entity, body.vat, body.vat_period, body.small_low_profit
    p.updated_at = utcnow()
    db.add(p)
    db.flush()
    return _dump_profile(p, user.id)


# ------------------------------------------------------------------ 记账底稿（OPC-101 / 102）
@router.get("/opc/entries")
def list_entries(period: str = Query(default="", max_length=7), kind: Literal["income", "expense"] | None = None,
                 limit: int = Query(default=200, ge=1, le=1000),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    q = db.query(OpcEntry).filter(OpcEntry.owner_id == user.id)
    if period:
        start, end, _ = svc.parse_period(_period(period))
        q = q.filter(OpcEntry.occurred_on >= start, OpcEntry.occurred_on <= end)
    if kind:
        q = q.filter(OpcEntry.kind == kind)
    return [_dump(e) for e in q.order_by(OpcEntry.occurred_on.desc(), OpcEntry.id.desc()).limit(limit)]


@router.post("/opc/entries", status_code=201)
def add_entry(body: EntryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    if (db.query(func.count(OpcEntry.id)).filter(OpcEntry.owner_id == user.id).scalar() or 0) >= LIMIT_ENTRIES:
        raise conflict(f"账目已达上限（{LIMIT_ENTRIES} 条），请先导出归档后删除旧的", "opc_limit_reached")
    if body.tax_cents > body.amount_cents:
        raise bad_request("税额不能大于含税金额", "opc_tax_exceeds_amount")
    e = OpcEntry(owner_id=user.id, source="manual", **body.model_dump())
    db.add(e)
    db.flush()
    return _dump(e)


@router.patch("/opc/entries/{entry_id}")
def patch_entry(entry_id: int, body: EntryPatch, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    e = _own(db, entry_id, user)
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if e.source == "platform" and {"amount_cents", "occurred_on"} & data.keys():
        raise conflict("平台导入的收入金额与日期以平台流水为准，不能改；可以补备注、发票号", "opc_platform_entry_locked")
    for k, v in data.items():
        setattr(e, k, v)
    if e.tax_cents > e.amount_cents:
        raise bad_request("税额不能大于含税金额", "opc_tax_exceeds_amount")
    db.add(e)
    db.flush()
    return _dump(e)


@router.delete("/opc/entries/{entry_id}")
def delete_entry(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    db.delete(_own(db, entry_id, user))
    return {"deleted": True}


@router.post("/opc/entries/import-platform")
def import_platform(body: ImportIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db, scope="function")):
    """把平台上已到账的报酬记进底稿（按流水去重，导几次都一样）。"""
    n = svc.import_platform(db, user.id, body.since)
    db.flush()
    return {"imported": n}


# ------------------------------------------------------------------ 汇总、导出、日历（OPC-103 / 104）
@router.get("/opc/summary")
def get_summary(period: str = Query(default="", max_length=7), user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    today = _today()
    return svc.summary(db, user.id, _period(period or svc.current_quarter(today)), _profile(db, user), today)


@router.get("/opc/export")
def export_csv(period: str = Query(max_length=7), user: User = Depends(get_current_user),
               db: Session = Depends(get_db, scope="function")):
    """底稿导出 CSV（交给记账代理或自己报税时对照）。"""
    start, end, _ = svc.parse_period(_period(period))
    rows = (db.query(OpcEntry).filter(OpcEntry.owner_id == user.id, OpcEntry.occurred_on >= start,
                                      OpcEntry.occurred_on <= end).order_by(OpcEntry.occurred_on, OpcEntry.id).all())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日期", "收支", "含税金额（元）", "税额（元）", "类别", "对方", "发票号", "发票类型", "来源", "备注"])
    names = {"income": "收入", "expense": "支出"}
    kinds = {"none": "无", "ordinary": "普通发票", "special": "专用发票"}
    for e in rows:
        w.writerow([day(e.occurred_on), names[e.kind], f"{e.amount_cents / 100:.2f}", f"{e.tax_cents / 100:.2f}",
                    e.category, e.counterparty, e.invoice_no, kinds.get(e.invoice_kind, e.invoice_kind),
                    "平台" if e.source == "platform" else "手记", e.note])
    return {"filename": f"opc-{period}.csv", "rows": len(rows), "csv": buf.getvalue()}


@router.get("/opc/calendar")
def get_calendar(days: int = Query(default=120, ge=7, le=400), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")):
    p = _profile(db, user)
    items = svc.deadlines(p or OpcProfile(user_id=user.id, entity="individual", vat="none", vat_period="quarter"),
                          _today(), days)
    return {"configured": p is not None, "items": items,
            "notice": "按你填的主体与纳税人类型推算，只覆盖最常见的申报；截止日遇法定节假日顺延，以电子税务局为准。"}


# ------------------------------------------------------------------ 合同体检（OPC-105）
@router.post("/opc/contract-review")
def contract_review(body: ReviewIn, user: User = Depends(get_current_user)):
    """合同原文不落库：体检完就丢。"""
    return svc.review_contract(body.text, body.role)
