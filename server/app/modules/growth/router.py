"""GRW 增长运营 API（22 号 spec）。

分两组：面向用户（领券/我的券/邀请战绩/新人任务）与面向运营
（建券、建活动、报表、市场健康度、北极星指标）。
运营组一律 `require_admin`——补贴是花钱的操作。
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, not_found
from app.modules.account.models import User, utcnow

from . import service
from .models import Campaign, Coupon, UserCoupon

router = APIRouter(tags=["growth"])


# ---------- 运营：券模板 ----------
class CouponIn(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    kind: str = Field(default="requester_discount", pattern="^(requester_discount|worker_bonus)$")
    amount_cents: int = Field(default=0, ge=0)
    percent_bps: int = Field(default=0, ge=0, lt=10000)
    max_discount_cents: int = Field(default=0, ge=0)
    min_order_cents: int = Field(default=0, ge=0)
    category: str = ""
    newcomer_only: bool = False
    total_quota: int = Field(default=0, ge=0)
    per_user_limit: int = Field(default=1, ge=1, le=10)
    valid_days: int = Field(default=30, ge=1, le=365)
    days_open: int = Field(default=30, ge=1, le=365)  # 领取窗口天数
    campaign_id: int | None = None


def _dump_coupon(c: Coupon) -> dict:
    return {
        "id": c.id, "title": c.title, "kind": c.kind, "amount_cents": c.amount_cents,
        "percent_bps": c.percent_bps, "max_discount_cents": c.max_discount_cents,
        "min_order_cents": c.min_order_cents, "category": c.category,
        "newcomer_only": c.newcomer_only, "total_quota": c.total_quota,
        "issued_count": c.issued_count, "per_user_limit": c.per_user_limit,
        "valid_days": c.valid_days, "active": c.active,
        "ends_at": c.ends_at.isoformat(), "campaign_id": c.campaign_id,
    }


@router.post("/admin/coupons", status_code=201)
def create_coupon(body: CouponIn, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """GRW-001/005 建券。比例券必须带封顶，否则大额单会失控。"""
    now = utcnow()
    fields = body.model_dump(exclude={"days_open"})
    coupon = service.create_coupon(db, **fields, starts_at=now,
                                   ends_at=now + timedelta(days=body.days_open))
    return _dump_coupon(coupon)


@router.post("/admin/coupons/{coupon_id}/pause")
def pause_coupon(coupon_id: int, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """GRW-005 暂停发放（已领取的券不受影响，不追溯作废用户已得权益）。"""
    coupon = db.get(Coupon, coupon_id)
    if not coupon:
        raise not_found("券不存在")
    coupon.active = False
    db.add(coupon)
    return _dump_coupon(coupon)


@router.get("/admin/coupons")
def coupon_report(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """GRW-005 发放/核销/成本报表：运营自己就能看清一张券花了多少钱。"""
    out = []
    for c in db.query(Coupon).order_by(Coupon.id.desc()).all():
        rows = db.query(UserCoupon).filter(UserCoupon.coupon_id == c.id).all()
        used = [r for r in rows if r.status == "used"]
        out.append({
            **_dump_coupon(c),
            "claimed": len(rows), "used": len(used),
            "cost_cents": sum(r.discount_cents for r in used),
            "use_rate": round(len(used) / len(rows), 4) if rows else 0.0,
        })
    return {"coupons": out}


# ---------- 运营：活动 ----------
class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = ""
    category: str = ""
    budget_cap_cents: int = Field(gt=0)
    days: int = Field(default=14, ge=1, le=180)


@router.post("/admin/campaigns", status_code=201)
def create_campaign(body: CampaignIn, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    """GRW-030 建活动：预算硬顶是必填项，超顶自动停投。"""
    now = utcnow()
    row = Campaign(name=body.name, city=body.city, category=body.category,
                   budget_cap_cents=body.budget_cap_cents, starts_at=now,
                   ends_at=now + timedelta(days=body.days), created_by=admin.id)
    db.add(row)
    db.flush()
    return _dump_campaign(row)


def _dump_campaign(c: Campaign) -> dict:
    return {
        "id": c.id, "name": c.name, "city": c.city, "category": c.category,
        "budget_cap_cents": c.budget_cap_cents, "spent_cents": c.spent_cents,
        "remaining_cents": max(0, c.budget_cap_cents - c.spent_cents),
        "active": c.active, "ends_at": c.ends_at.isoformat(),
    }


@router.get("/admin/campaigns")
def list_campaigns(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"campaigns": [_dump_campaign(c) for c in db.query(Campaign)
                          .order_by(Campaign.id.desc()).all()]}


class FundIn(BaseModel):
    amount_cents: int = Field(gt=0)


@router.post("/admin/subsidy-pool/fund")
def fund_subsidy_pool(body: FundIn, admin: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    """GRW-003 补贴池注资：冷启动时平台还没有佣金收入，得先注资才能发券。"""
    from app.modules.wallet import service as wallet

    return wallet.fund_platform(db, body.amount_cents, memo=f"补贴池注资（管理员 {admin.id}）")


# ---------- 运营：看板 ----------
@router.get("/admin/market-health")
def market_health(days: int = Query(default=30, ge=1, le=365),
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """GRW-022 供需健康度：按城市×类目标出供给缺口与需求缺口。"""
    return service.market_health(db, days)


@router.get("/admin/north-star")
def north_star(days: int = Query(default=30, ge=1, le=365),
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """GRW-052 北极星指标：成单数与成单 GMV。"""
    return service.north_star(db, days)


# ---------- 用户：券 ----------
@router.get("/coupons")
def available_coupons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """可领取的券（已领满或已领完的不再展示，避免点了才知道拿不到）。"""
    now = utcnow()
    out = []
    for c in db.query(Coupon).filter(Coupon.active.is_(True)).all():
        if not (c.starts_at <= now <= c.ends_at):
            continue
        if c.total_quota and c.issued_count >= c.total_quota:
            continue
        held = db.query(UserCoupon).filter(UserCoupon.coupon_id == c.id,
                                           UserCoupon.user_id == user.id).count()
        if held >= c.per_user_limit:
            continue
        out.append(_dump_coupon(c))
    return {"coupons": out}


@router.post("/coupons/{coupon_id}/claim", status_code=201)
def claim_coupon(coupon_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """GRW-002 领取（幂等由每人限领上限约束）。"""
    row = service.claim(db, coupon_id, user)
    return {"id": row.id, "coupon_id": row.coupon_id, "status": row.status,
            "expires_at": row.expires_at.isoformat()}


@router.get("/me/coupons")
def my_coupons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = utcnow()
    out = []
    for r in db.query(UserCoupon).filter(UserCoupon.user_id == user.id) \
               .order_by(UserCoupon.id.desc()).all():
        coupon = db.get(Coupon, r.coupon_id)
        status = r.status
        if status == "unused" and r.expires_at <= now:
            status = "expired"
        out.append({
            "id": r.id, "status": status, "title": coupon.title if coupon else "",
            "kind": coupon.kind if coupon else "", "min_order_cents":
                coupon.min_order_cents if coupon else 0,
            "amount_cents": coupon.amount_cents if coupon else 0,
            "percent_bps": coupon.percent_bps if coupon else 0,
            "max_discount_cents": coupon.max_discount_cents if coupon else 0,
            "category": coupon.category if coupon else "",
            "expires_at": r.expires_at.isoformat(),
            "discount_cents": r.discount_cents, "contract_id": r.contract_id,
        })
    return {"coupons": out}


@router.get("/contracts/{contract_id}/coupons")
def usable_for_contract(contract_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """下单前告诉用户这一单能用哪张、能省多少——不能用的不展示。"""
    from app.modules.contract.models import Contract
    from app.modules.task.models import Task

    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id):
        raise bad_request("非合约当事人", "not_party")
    task = db.get(Task, contract.task_id)
    category = task.category if task else ""
    want_kind = "requester_discount" if user.id == contract.requester_id else "worker_bonus"

    now = utcnow()
    out = []
    for r in db.query(UserCoupon).filter(UserCoupon.user_id == user.id,
                                         UserCoupon.status == "unused").all():
        coupon = db.get(Coupon, r.coupon_id)
        if not coupon or coupon.kind != want_kind or r.expires_at <= now:
            continue
        if contract.amount_cents < coupon.min_order_cents:
            continue
        if coupon.category and coupon.category != category:
            continue
        out.append({"user_coupon_id": r.id, "title": coupon.title,
                    "discount_cents": service.discount_for(coupon, contract.amount_cents)})
    out.sort(key=lambda x: -x["discount_cents"])
    return {"usable": out}


# ---------- 用户：邀请与新人 ----------
@router.get("/me/referrals")
def my_referrals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GRW-014 邀请战绩。`levels: 1` 是合规声明：奖励**仅一级**。"""
    return service.referral_stats(db, user.id)


@router.get("/me/newcomer")
def my_newcomer_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GRW-020 新人任务清单与进度。"""
    return service.newcomer_progress(db, user)


@router.get("/market/supply-hint")
def supply_hint(city: str = "", category: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GRW-023 发布页提示：该区域执行人少时提前告知，别让发布方空等。"""
    return {"hint": service.supply_hint_text(db, city, category)}
