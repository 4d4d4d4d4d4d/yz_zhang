"""GRW 增长运营服务层。

补贴资金流的唯一形态：**平台账户 → 用户可用余额**，走 `wallet.transfer`，
落 `subsidy` 流水。这样做的好处是补贴天然被资金四不变量约束——
任何一分补贴都能追到出资方，不存在「凭空多出来的钱」。
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.modules.account.models import User, utcnow
from app.modules.wallet import service as wallet
from app.modules.wallet.service import PLATFORM_USER_ID

from .models import Campaign, Coupon, ReferralReward, UserCoupon

# GRW-012 邀请奖励金额（分）。刻意做成常量而非可配：分销层级与金额是合规敏感项，
# 改动应经过评审而不是运营后台随手调。
REFERRAL_REWARD_CENTS = 1000


# ---------- 券模板 ----------
def create_coupon(db: Session, **fields) -> Coupon:
    amount = fields.get("amount_cents", 0)
    percent = fields.get("percent_bps", 0)
    if (amount > 0) == (percent > 0):
        raise bad_request("定额与比例二选一", "invalid_coupon_value")
    if percent > 0 and fields.get("max_discount_cents", 0) <= 0:
        # 没有封顶的比例券遇到大额单会失控，这是运营事故的常见来源
        raise bad_request("比例券必须设置封顶金额", "percent_needs_cap")
    if percent >= 10000:
        raise bad_request("折扣比例必须小于 100%", "invalid_percent")
    coupon = Coupon(**fields)
    db.add(coupon)
    db.flush()
    return coupon


def discount_for(coupon: Coupon, order_cents: int) -> int:
    """给定订单金额算出实际优惠额（比例券按封顶截断，且不超过订单本身）。"""
    if coupon.amount_cents > 0:
        value = coupon.amount_cents
    else:
        value = order_cents * coupon.percent_bps // 10000
        value = min(value, coupon.max_discount_cents)
    return max(0, min(value, order_cents))


# ---------- 领取 ----------
def claim(db: Session, coupon_id: int, user: User) -> UserCoupon:
    coupon = db.get(Coupon, coupon_id)
    if not coupon or not coupon.active:
        raise not_found("券不存在或已下架", "coupon_unavailable")
    now = utcnow()
    if not (coupon.starts_at <= now <= coupon.ends_at):
        raise conflict("不在领取时间内", "coupon_window_closed")
    if coupon.total_quota and coupon.issued_count >= coupon.total_quota:
        raise conflict("已被领完", "coupon_exhausted")
    if coupon.newcomer_only and _has_completed_task(db, user.id):
        raise conflict("仅限新用户领取", "newcomer_only")

    held = (
        db.query(UserCoupon)
        .filter(UserCoupon.coupon_id == coupon.id, UserCoupon.user_id == user.id)
        .count()
    )
    if held >= coupon.per_user_limit:
        raise conflict("已达每人领取上限", "per_user_limit")
    # GRW-004 反刷：未实名账号不得领券（否则批量注册即可薅）
    if not user.is_verified:
        raise conflict("请先完成实名认证再领取", "verification_required")

    row = UserCoupon(
        coupon_id=coupon.id, user_id=user.id,
        expires_at=min(now + timedelta(days=coupon.valid_days), coupon.ends_at),
    )
    coupon.issued_count += 1
    db.add_all([row, coupon])
    db.flush()
    return row


def _has_completed_task(db: Session, user_id: int) -> bool:
    from app.modules.task.models import Task

    return (
        db.query(Task)
        .filter(Task.status == "completed",
                (Task.creator_id == user_id) | (Task.executor_id == user_id))
        .first()
        is not None
    )


# ---------- 核销 ----------
def _usable(db: Session, uc: UserCoupon, coupon: Coupon, order_cents: int, category: str) -> None:
    now = utcnow()
    if uc.status != "unused":
        raise conflict("该券已使用或已失效", "coupon_used")
    if uc.expires_at <= now:
        raise conflict("该券已过期", "coupon_expired")
    if order_cents < coupon.min_order_cents:
        raise bad_request(f"订单需满 {coupon.min_order_cents / 100:.2f} 元可用", "below_min_order")
    if coupon.category and coupon.category != category:
        raise bad_request(f"该券仅限「{coupon.category}」类目", "category_mismatch")


def redeem(db: Session, user_coupon_id: int, user_id: int, contract, category: str) -> int:
    """GRW-002/003 核销：平台出资打给用户，绑定合约，返回优惠额。

    调用点在托管（发布方立减）与放款（接单方补贴），因此这里只管
    「平台掏钱 → 用户到账 → 券置为已用」，不碰托管账目本身，
    托管口径（Σescrow == Σ未放款合约额）因此天然不受影响。
    """
    uc = db.get(UserCoupon, user_coupon_id)
    if not uc or uc.user_id != user_id:
        raise not_found("券不存在", "coupon_not_found")
    coupon = db.get(Coupon, uc.coupon_id)
    if not coupon:
        raise not_found("券模板不存在", "coupon_not_found")
    _usable(db, uc, coupon, contract.amount_cents, category)

    if db.query(UserCoupon).filter(UserCoupon.contract_id == contract.id).first():
        raise conflict("该订单已使用过优惠券（一单一券）", "coupon_already_applied")

    value = discount_for(coupon, contract.amount_cents)
    if value <= 0:
        raise bad_request("该券在本单无可用优惠", "no_discount")

    campaign = db.get(Campaign, coupon.campaign_id) if coupon.campaign_id else None
    if campaign:
        _check_campaign(campaign, value)

    # GRW-003 资金口径：平台账户余额不足则核销失败，绝不透支
    platform = wallet.get_or_create(db, PLATFORM_USER_ID)
    if platform.available_cents < value:
        raise conflict("平台补贴额度不足，请稍后再试", "subsidy_pool_exhausted")
    wallet.transfer(db, PLATFORM_USER_ID, user_id, value, contract.id,
                    memo=f"优惠券补贴 #{uc.id}", kind="subsidy")

    uc.status = "used"
    uc.contract_id = contract.id
    uc.discount_cents = value
    uc.used_at = utcnow()
    db.add(uc)
    if campaign:
        campaign.spent_cents += value
        if campaign.spent_cents >= campaign.budget_cap_cents:
            campaign.active = False  # GRW-030 超顶自动停投
        db.add(campaign)
    db.flush()
    return value


def _check_campaign(campaign: Campaign, value: int) -> None:
    now = utcnow()
    if not campaign.active or not (campaign.starts_at <= now <= campaign.ends_at):
        raise conflict("活动已结束", "campaign_closed")
    if campaign.spent_cents + value > campaign.budget_cap_cents:
        raise conflict("活动预算已用尽", "campaign_budget_exhausted")


def release_on_cancel(db: Session, contract_id: int) -> None:
    """GRW-002 合约取消 → 券退回可再用（有效期不变，不因平台侧取消而变相作废）。

    补贴款一并退回平台账户，否则用户白拿一笔钱。
    """
    uc = db.query(UserCoupon).filter(UserCoupon.contract_id == contract_id).first()
    if not uc or uc.status != "used":
        return
    if uc.discount_cents > 0:
        wallet.transfer(db, uc.user_id, PLATFORM_USER_ID, uc.discount_cents, contract_id,
                        memo=f"优惠券退回 #{uc.id}", kind="subsidy")
        coupon = db.get(Coupon, uc.coupon_id)
        if coupon and coupon.campaign_id:
            campaign = db.get(Campaign, coupon.campaign_id)
            if campaign:
                campaign.spent_cents = max(0, campaign.spent_cents - uc.discount_cents)
                db.add(campaign)
    uc.status = "unused"
    uc.contract_id = None
    uc.discount_cents = 0
    uc.used_at = None
    db.add(uc)
    db.flush()


# ---------- 邀请奖励 ----------
def grant_referral(db: Session, invitee: User) -> ReferralReward | None:
    """GRW-012/013/060 被邀请人完成首单 → 邀请人得现金奖励。

    三条硬约束：
    1. **仅一级**——邀请人的邀请人不得任何奖励（代码层面就不去找，见 GRW-060）
    2. 每个被邀请人只发一次（`invitee_id` 唯一约束）
    3. 反作弊命中（同收款账户 / 互为邀请）→ blocked 进人工，不发钱
    """
    if not invitee.referred_by or invitee.referral_rewarded:
        return None
    inviter = db.get(User, invitee.referred_by)
    if not inviter or inviter.is_banned:
        return None

    reason = _fraud_reason(db, inviter, invitee)
    reward = ReferralReward(
        inviter_id=inviter.id, invitee_id=invitee.id,
        amount_cents=REFERRAL_REWARD_CENTS,
        status="blocked" if reason else "granted", reason=reason,
    )
    invitee.referral_rewarded = True
    db.add_all([reward, invitee])

    if not reason:
        platform = wallet.get_or_create(db, PLATFORM_USER_ID)
        if platform.available_cents < REFERRAL_REWARD_CENTS:
            reward.status = "blocked"
            reward.reason = "平台补贴额度不足，待补充后人工发放"
        else:
            wallet.transfer(db, PLATFORM_USER_ID, inviter.id, REFERRAL_REWARD_CENTS,
                            None, memo=f"邀请奖励（被邀请人 {invitee.id}）", kind="subsidy")
            from app.modules.notification.service import notify

            notify(db, inviter.id, "system", "邀请奖励到账",
                   f"你邀请的「{invitee.nickname}」完成首单，"
                   f"奖励 {REFERRAL_REWARD_CENTS / 100:.2f} 元已到账")
    db.flush()
    return reward


def _fraud_reason(db: Session, inviter: User, invitee: User) -> str:
    """GRW-013 反作弊：能自动判定的先拦下，交人工。"""
    from app.modules.wallet.models import PayoutAccount

    if inviter.referred_by == invitee.id:
        return "互为邀请人，疑似刷单成环"
    a = db.get(PayoutAccount, inviter.id)
    b = db.get(PayoutAccount, invitee.id)
    if a and b and a.account_no == b.account_no:
        return "邀请双方使用同一收款账户"
    if inviter.id_digest and inviter.id_digest == invitee.id_digest:
        return "邀请双方实名信息相同"
    return ""


def referral_stats(db: Session, user_id: int) -> dict:
    """GRW-014 邀请战绩页。"""
    invited = db.query(User).filter(User.referred_by == user_id).all()
    rewards = db.query(ReferralReward).filter(ReferralReward.inviter_id == user_id).all()
    granted = [r for r in rewards if r.status == "granted"]
    return {
        "referral_code": db.get(User, user_id).referral_code,
        "invited_count": len(invited),
        "achieved_count": len(granted),
        "blocked_count": len(rewards) - len(granted),
        "earned_cents": sum(r.amount_cents for r in granted),
        # GRW-060 合规：明确告知只有一级，杜绝「拉人头分层返利」的想象空间
        "levels": 1,
    }


# ---------- 新人任务与市场健康度 ----------
NEWCOMER_STEPS = (
    ("profile", "完善昵称与城市"),
    ("verified", "完成实名认证"),
    ("skills", "设置技能标签"),
    ("first_publish", "发布第一个任务"),
    ("first_apply", "报名第一个任务"),
    ("first_done", "完成第一单"),
)


def newcomer_progress(db: Session, user: User) -> dict:
    """GRW-020 新人任务清单：进度可见才有牵引力。"""
    from app.modules.task.models import Application, Task

    done = {
        "profile": bool(user.nickname and user.city),
        "verified": user.is_verified,
        "skills": bool(user.skills),
        "first_publish": db.query(Task).filter(Task.creator_id == user.id).first() is not None,
        "first_apply": db.query(Application).filter(
            Application.applicant_id == user.id).first() is not None,
        "first_done": _has_completed_task(db, user.id),
    }
    steps = [{"key": k, "label": label, "done": done[k]} for k, label in NEWCOMER_STEPS]
    finished = sum(1 for s in steps if s["done"])
    return {"steps": steps, "finished": finished, "total": len(steps),
            "completed": finished == len(steps)}


MIN_SUPPLY = 3  # GRW-023 某城市某类目可接单人数低于此值即视为供给不足


def market_health(db: Session, days: int = 30) -> dict:
    """GRW-022 供需健康度：按城市×类目找出**供给缺口**与**需求缺口**。

    双边市场的死法几乎都是「某个格子里只有一边」，所以这张表要能一眼
    看出往哪投钱：供给不足就补执行者，需求不足就补发布方。
    """
    from sqlalchemy import func

    from app.modules.task.models import Application, Task

    since = utcnow() - timedelta(days=days)
    rows = (
        db.query(Task.city, Task.category, func.count(Task.id))
        .filter(Task.created_at >= since)
        .group_by(Task.city, Task.category)
        .all()
    )
    out = []
    for city, category, published in rows:
        task_ids = [
            t.id for t in db.query(Task.id)
            .filter(Task.city == city, Task.category == category, Task.created_at >= since)
            .all()
        ]
        workers = (
            db.query(func.count(func.distinct(Application.applicant_id)))
            .filter(Application.task_id.in_(task_ids)).scalar() or 0
        )
        matched = (
            db.query(func.count(Task.id))
            .filter(Task.id.in_(task_ids), Task.executor_id.isnot(None)).scalar() or 0
        )
        gap = ""
        if workers < MIN_SUPPLY:
            gap = "supply"      # 有需求没人接
        elif published < MIN_SUPPLY:
            gap = "demand"      # 有人没活干
        out.append({
            "city": city or "(未填)", "category": category,
            "published": int(published), "active_workers": int(workers),
            "matched": int(matched),
            "fill_rate": round(matched / published, 4) if published else 0.0,
            "gap": gap,
        })
    out.sort(key=lambda r: (-r["published"], r["city"]))
    return {"window_days": days, "min_supply": MIN_SUPPLY, "cells": out}


def supply_hint_text(db: Session, city: str, category: str) -> str:
    """GRW-023 发布页提示：该区域执行人少时提前告知，别让发布方空等。"""
    if not city or not category:
        return ""
    cells = {(c["city"], c["category"]): c for c in market_health(db)["cells"]}
    cell = cells.get((city, category))
    if cell and cell["active_workers"] < MIN_SUPPLY:
        return f"该区域「{category}」执行人较少（近 30 天 {cell['active_workers']} 人），可能响应较慢"
    return ""


# ---------- 北极星指标 ----------
def north_star(db: Session, days: int = 30) -> dict:
    """GRW-052 北极星：成单数与成单 GMV；次级指标看转化与健康。"""
    from sqlalchemy import func

    from app.modules.contract.models import Contract
    from app.modules.dispute.models import Dispute
    from app.modules.task.models import Task

    since = utcnow() - timedelta(days=days)
    completed = db.query(Task).filter(Task.status == "completed",
                                      Task.completed_at >= since).all()
    gmv = (
        db.query(func.coalesce(func.sum(Contract.released_cents), 0))
        .filter(Contract.closed_at >= since).scalar() or 0
    )
    new_users = db.query(User).filter(User.created_at >= since).all()
    first_order = sum(1 for u in new_users if _has_completed_task(db, u.id))
    disputes = db.query(func.count(Dispute.id)).filter(Dispute.created_at >= since).scalar() or 0
    return {
        "window_days": days,
        "orders_completed": len(completed),          # 北极星 1
        "gmv_cents": int(gmv),                       # 北极星 2
        "new_users": len(new_users),
        "new_user_first_order_rate": round(first_order / len(new_users), 4) if new_users else 0.0,
        "dispute_rate": round(disputes / len(completed), 4) if completed else 0.0,
    }
