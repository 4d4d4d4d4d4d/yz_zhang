from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.vendors import sms_service
from app.core.errors import bad_request, conflict, not_found
from app.core.security import create_token, hash_password, verify_password

from .models import Block, LoginSession, User
from .service import credit_level

router = APIRouter(tags=["account"])


def _issue_token(db: Session, user: User, device: str) -> str:
    """ACC-005：每次登录建立会话，token 绑定会话可被吊销。
    ACC-007：老账号在陌生设备登录 → 站内通知提醒（业界安全惯例）。"""
    device = device[:200]
    known = db.query(LoginSession).filter(LoginSession.user_id == user.id).count()
    seen_device = (
        db.query(LoginSession)
        .filter(LoginSession.user_id == user.id, LoginSession.device == device)
        .first()
    )
    session = LoginSession(user_id=user.id, device=device)
    db.add(session)
    db.flush()
    if known and not seen_device:
        from app.modules.notification.service import notify

        notify(db, user.id, "account", "新设备登录提醒",
               f"你的账号刚在新设备登录（{device[:60] or '未知设备'}）。"
               "若非本人操作，请立即修改密码并在「登录设备」中下线该会话。")
    return create_token(user.id, session.id)


# ---------- schemas ----------
class RegisterIn(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(default="", max_length=50)
    sms_code: str
    referral_code: str = ""  # CNT-022 邀请码（可选）


class LoginIn(BaseModel):
    phone: str
    password: str


class SmsLoginIn(BaseModel):
    phone: str
    sms_code: str


class ProfileUpdateIn(BaseModel):
    nickname: str | None = None
    bio: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    skills: list[str] | None = None
    interests: list[str] | None = None
    privacy: dict | None = None
    service_rate_cents: int | None = None
    available_times: str | None = None
    accepting_orders: bool | None = None  # ACC-014 接单开关（下线不进推荐/不可被邀约）


class VerifyIn(BaseModel):
    real_name: str = Field(min_length=2, max_length=50)
    id_number: str = Field(min_length=15, max_length=18)


class CertificationIn(BaseModel):
    name: str = Field(min_length=2, max_length=30)  # 如：律师 / 电工
    license_no: str = Field(min_length=4, max_length=50)


def _me(user: User) -> dict:
    return {
        "id": user.id,
        "phone": user.phone[:3] + "****" + user.phone[-4:],
        "nickname": user.nickname,
        "bio": user.bio,
        "city": user.city,
        "lat": user.lat,
        "lng": user.lng,
        "skills": user.skills,
        "interests": user.interests,
        "is_verified": user.is_verified,
        "is_admin": user.is_admin,
        "certifications": user.certifications,
        "credit_score": user.credit_score,
        "credit_level": credit_level(user.credit_score),
        "rating_avg": user.rating_avg,
        "tasks_completed": user.tasks_completed,
        "referral_code": user.referral_code,
    }


# ---------- auth (ACC-001/002) ----------
class SendCodeIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    scene: str = Field(default="verify", pattern="^(verify|login|reset|change_phone)$")


@router.post("/auth/send-code")
def send_sms_code(request: Request, body: SendCodeIn, db: Session = Depends(get_db)):
    """VND-020 请求短信验证码。模拟通道回显 `dev_code` 便于开发；真实通道不回显。

    限流与注册/登录同级，防被当作短信轰炸机（费用与骚扰双重风险）。
    """
    from app.core.guard import guard
    from app.vendors.base import VendorError

    # SEC-011 双维度：换号不换 IP 也挡得住（短信费与骚扰是双重代价）
    guard(request, "send-code", body.phone, limit=3, ip_limit=10)
    try:
        return sms_service.send_code(db, body.phone, body.scene)
    except VendorError as exc:
        raise exc.as_http() from exc


@router.post("/auth/register", status_code=201)
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    # ACC-001/SEC-011 防刷：账号 + IP 双维度。只按手机号限挡不住批量注册——
    # 攻击者每次换号，账号维度的计数器永远是 1
    from app.core.guard import guard

    guard(request, "register", body.phone, limit=3, ip_limit=10)
    sms_service.verify_code(db, body.phone, body.sms_code)
    if db.query(User).filter(User.phone == body.phone).first():
        raise conflict("手机号已注册", "phone_taken")
    referrer = None
    if body.referral_code:
        referrer = db.query(User).filter(User.referral_code == body.referral_code).first()
    user = User(
        phone=body.phone,
        password_hash=hash_password(body.password),
        nickname=body.nickname or f"用户{body.phone[-4:]}",
        referred_by=referrer.id if referrer else None,
    )
    db.add(user)
    db.flush()
    # CNT-022 生成本人邀请码（基于 id，稳定唯一）
    user.referral_code = f"R{user.id:06d}"
    db.add(user)
    # LAW-030 注册页展示协议，注册即同意当前版本（敏感项不在此列，须单独同意）
    from app.modules.legal import consent

    consent.grant_registration_consents(db, user.id)
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


@router.post("/auth/login")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    # ACC-002/SEC-011/020 防撞库：双维度限流 + 失败计数自动封禁 IP
    from app.core.clientip import client_ip
    from app.core.guard import guard, note_auth_failure, note_auth_success

    guard(request, "login-pwd", body.phone, limit=5, ip_limit=20)
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user or user.is_deleted or not verify_password(body.password, user.password_hash):
        note_auth_failure(client_ip(request))
        raise bad_request("手机号或密码错误", "bad_credentials")
    note_auth_success(client_ip(request))
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


@router.post("/auth/login-sms")
def login_sms(request: Request, body: SmsLoginIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    """验证码登录，未注册自动注册（ACC-001）。"""
    from app.core.guard import guard

    guard(request, "login-sms", body.phone, limit=5, ip_limit=20)
    sms_service.verify_code(db, body.phone, body.sms_code)
    user = db.query(User).filter(User.phone == body.phone).first()
    if user and user.is_deleted:
        raise bad_request("账号已注销", "account_deleted")
    if not user:
        user = User(phone=body.phone, nickname=f"用户{body.phone[-4:]}")
        db.add(user)
        db.flush()
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


# ---------- 密码管理（ACC-004）----------
class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)


class ResetPasswordIn(BaseModel):
    phone: str
    sms_code: str
    new_password: str = Field(min_length=6, max_length=64)


@router.post("/auth/change-password")
def change_password(request: Request, 
    body: ChangePasswordIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), user_agent: str = Header(default=""),
):
    """ACC-004 修改密码：验证旧密码；成功后吊销全部会话并签发新 token（业界惯例）。"""
    if not user.password_hash or not verify_password(body.old_password, user.password_hash):
        raise bad_request("原密码错误", "bad_old_password")
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.query(LoginSession).filter(
        LoginSession.user_id == user.id, LoginSession.revoked.is_(False)
    ).update({"revoked": True})
    return {"token": _issue_token(db, user, user_agent)}


class ChangePhoneIn(BaseModel):
    new_phone: str = Field(min_length=5, max_length=20)
    sms_code: str  # 发往新号的验证码
    password: str  # 旧密码二次确认（业界惯例：改绑登录身份需强校验）


@router.post("/auth/change-phone")
def change_phone(request: Request, 
    body: ChangePhoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """ACC-008 换绑手机：新号验证码 + 旧密码双重校验；新号不可已被占用。"""
    from app.core.guard import guard

    guard(request, "change-phone", str(user.id), limit=3, ip_limit=10)
    sms_service.verify_code(db, body.new_phone, body.sms_code, scene="change_phone")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise bad_request("密码错误", "bad_password")
    if body.new_phone == user.phone:
        raise bad_request("新手机号与当前一致", "same_phone")
    if db.query(User).filter(User.phone == body.new_phone).first():
        raise conflict("该手机号已被占用", "phone_taken")
    user.phone = body.new_phone
    db.add(user)
    from app.modules.notification.service import notify

    notify(db, user.id, "account", "手机号已换绑",
           f"你的登录手机号已成功换绑为 {body.new_phone[:3]}****{body.new_phone[-4:]}。"
           "若非本人操作，请立即联系客服。")
    return {"ok": True, "phone": user.phone[:3] + "****" + user.phone[-4:]}


@router.post("/auth/reset-password")
def reset_password(request: Request, body: ResetPasswordIn, db: Session = Depends(get_db)):
    """ACC-004 忘记密码：短信码重置；吊销全部会话，需重新登录（业界惯例）。"""
    from app.core.guard import guard

    guard(request, "reset-pwd", body.phone, limit=3, ip_limit=10)
    sms_service.verify_code(db, body.phone, body.sms_code)
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user or user.is_deleted:
        raise bad_request("账号不存在", "no_such_account")
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.query(LoginSession).filter(
        LoginSession.user_id == user.id, LoginSession.revoked.is_(False)
    ).update({"revoked": True})
    return {"ok": True}


# ---------- 会话/设备管理（ACC-005）----------
@router.get("/auth/sessions")
def my_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(LoginSession)
        .filter(LoginSession.user_id == user.id, LoginSession.revoked.is_(False))
        .order_by(LoginSession.id.desc())
        .all()
    )
    return [
        {"id": s.id, "device": s.device or "未知设备", "created_at": s.created_at.isoformat()}
        for s in rows
    ]


@router.post("/auth/sessions/{session_id}/revoke")
def revoke_session(
    session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session = db.get(LoginSession, session_id)
    if not session or session.user_id != user.id:
        raise not_found("会话不存在")
    session.revoked = True
    db.add(session)
    return {"ok": True}


# ---------- 账号注销（ACC-006）----------
@router.post("/users/me/deactivate")
def deactivate_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """注销：有未结算合约或进行中纠纷时阻断；通过后脱敏并吊销全部会话。"""
    from app.modules.contract.models import Contract
    from app.modules.dispute.models import Dispute
    from app.modules.wallet import service as wallet

    active_contract = (
        db.query(Contract)
        .filter(
            (Contract.requester_id == user.id) | (Contract.executor_id == user.id),
            Contract.status.in_(["pending_signatures", "signed", "funded"]),
        )
        .first()
    )
    if active_contract:
        raise conflict("存在未结算合约，请先完成或取消后再注销", "active_contract")
    open_dispute = (
        db.query(Dispute)
        .join(Contract, Contract.id == Dispute.contract_id)
        .filter(
            (Contract.requester_id == user.id) | (Contract.executor_id == user.id),
            Dispute.status == "open",
        )
        .first()
    )
    if open_dispute:
        raise conflict("存在进行中纠纷，结案后方可注销", "open_dispute")
    acct = wallet.get_or_create(db, user.id)
    if acct.available_cents > 0:
        raise conflict("钱包仍有余额，请先提现", "balance_remaining")
    # 脱敏保留（审计要求保留交易记录，个人身份信息清除）
    user.is_deleted = True
    user.phone = f"deleted:{user.id}"
    user.nickname = "已注销用户"
    user.real_name = ""
    user.bio = ""
    user.lat = None
    user.lng = None
    db.add(user)
    db.query(LoginSession).filter(LoginSession.user_id == user.id).update({"revoked": True})
    return {"deleted": True}


# ---------- profile (ACC-010/011/015) ----------
@router.get("/users/me")
def get_me(user: User = Depends(get_current_user)):
    return _me(user)


@router.patch("/users/me")
def update_me(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.add(user)
    return _me(user)


# ---------- 实名认证（ACC-020，模拟 eKYC）----------
@router.post("/users/me/verify")
def verify_identity(
    body: VerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """ACC-020 / VND-022 实名核验：走 `KycProvider` 抽象（模拟通道格式合法即通过）。

    VND-023：证件号**不落明文**，只存不可逆摘要（用于查重与风控关联）与掩码串。
    """
    from app.vendors import base as vendor_base
    from app.vendors.base import VendorError
    from app.vendors.kyc import id_digest, id_mask
    from app.vendors.registry import get_provider

    if user.is_verified:
        raise conflict("已完成实名认证", "already_verified")
    # LAW-031 证件是敏感个人信息：提交本表单即构成对该项的**单独同意**
    # （单独告知 + 单独行为），并留痕以备举证
    from app.modules.legal import consent

    consent.ensure(db, user.id, "identity")
    provider = get_provider("kyc")
    try:
        result = vendor_base.call(
            db, "kyc", provider.name, "verify",
            {"real_name": body.real_name, "id_no": body.id_number},
            lambda: provider.verify(body.real_name, body.id_number),
            idem_key=f"kyc:{id_digest(body.id_number)}",
        )
    except VendorError as exc:
        raise exc.as_http() from exc
    if result.status == "failed":
        raise bad_request("实名信息核验未通过，请核对姓名与证件号", "kyc_failed")
    if result.status == "manual":
        return {"is_verified": False, "status": "manual_review"}
    # 同一证件号不得绑定多个账号（防批量刷号/一人多号套补贴）
    digest = id_digest(body.id_number)
    taken = db.query(User).filter(User.id_digest == digest, User.id != user.id).first()
    if taken:
        raise conflict("该证件号已绑定其它账号", "id_already_bound")
    # LAW-005 未成年人不得接单：出生日期从证件号派生，**只存成年标记不存明文**
    if not _is_adult(body.id_number):
        raise bad_request(
            "未满 18 周岁不能完成实名认证与接单（涉及合同行为能力与用工合规）",
            "minor_not_allowed",
        )
    user.is_verified = True
    user.real_name = body.real_name
    user.id_digest = digest
    user.id_masked = id_mask(body.id_number)
    user.is_adult = True
    db.add(user)
    return {"is_verified": True}


def _is_adult(id_number: str) -> bool:
    """LAW-005 从 18 位证件号第 7~14 位取出生日期判断是否成年。

    格式不可解析时**放行**：拦截应基于确证的事实，而不是解析失败的猜测；
    真实 eKYC 供应商会直接返回出生日期，届时改用它更可靠。
    """
    from datetime import date

    if len(id_number) != 18 or not id_number[6:14].isdigit():
        return True
    try:
        born = date(int(id_number[6:10]), int(id_number[10:12]), int(id_number[12:14]))
    except ValueError:
        return True
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age >= 18


# ---------- 黑名单（ACC-033）----------
@router.post("/users/{user_id}/block")
def toggle_block(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id == user.id:
        raise bad_request("不能拉黑自己", "self_block")
    if not db.get(User, user_id):
        raise not_found("用户不存在")
    existing = (
        db.query(Block).filter(Block.blocker_id == user.id, Block.blocked_id == user_id).first()
    )
    if existing:
        db.delete(existing)
        return {"blocked": False}
    db.add(Block(blocker_id=user.id, blocked_id=user_id))
    return {"blocked": True}


@router.get("/users/me/blocks")
def my_blocks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Block).filter(Block.blocker_id == user.id).all()
    out = []
    for r in rows:
        u = db.get(User, r.blocked_id)
        out.append({"user_id": r.blocked_id, "nickname": u.nickname if u else ""})
    return out


# ---------- 职业资质认证（ACC-022，模拟审核即通过）----------
@router.post("/users/me/certifications", status_code=201)
def add_certification(
    body: CertificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """受限类目（法律咨询/电工等）接单准入凭证。生产接资质核验机构。"""
    if not user.is_verified:
        raise conflict("需先完成实名认证", "verification_required")
    if body.name in user.certifications:
        raise conflict("已有该资质", "certification_exists")
    user.certifications = user.certifications + [body.name]
    db.add(user)
    return {"certifications": user.certifications}


# ---------- 个人数据导出（ACC-031，PIPL/GDPR）----------
@router.get("/users/me/export")
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.modules.content.models import Content
    from app.modules.legal.consent import UserConsent
    from app.modules.task.models import Review, Task
    from app.modules.wallet.models import LedgerEntry

    tasks = db.query(Task).filter(
        (Task.creator_id == user.id) | (Task.executor_id == user.id)
    ).all()
    ledger = db.query(LedgerEntry).filter(LedgerEntry.user_id == user.id).all()
    contents = db.query(Content).filter(Content.author_id == user.id).all()
    reviews = db.query(Review).filter(Review.reviewer_id == user.id).all()
    return {
        "profile": _me(user),
        "real_name": user.real_name,
        "tasks": [{"id": t.id, "title": t.title, "status": t.status, "budget_cents": t.budget_cents,
                   "role": "creator" if t.creator_id == user.id else "executor"} for t in tasks],
        "ledger": [{"kind": e.kind, "amount_cents": e.amount_cents,
                    "created_at": e.created_at.isoformat()} for e in ledger],
        "contents": [{"id": c.id, "kind": c.kind, "body": c.body,
                      "created_at": c.created_at.isoformat()} for c in contents],
        "reviews_written": [{"task_id": r.task_id, "stars": r.stars, "comment": r.comment}
                            for r in reviews],
        # LAW-032 同意记录本身也是个人信息，且是「平台凭什么处理我的数据」的答案，
        # 导出里少了它，用户就没法核对平台的处理是否越界
        "consents": [
            {"scope": c.scope, "version": c.version, "notice": c.notice,
             "granted_at": c.granted_at.isoformat(),
             "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None}
            for c in db.query(UserConsent).filter(UserConsent.user_id == user.id)
            .order_by(UserConsent.id).all()
        ],
    }


# ---------- 公开名片与信用摘要（CRED-006）----------
@router.get("/users/{user_id}")
def public_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    base = {
        "id": user.id,
        "nickname": user.nickname,
        "is_verified": user.is_verified,
        "credit_score": user.credit_score,
        "credit_level": credit_level(user.credit_score),
        "rating_avg": user.rating_avg,
        "tasks_completed": user.tasks_completed,
    }
    # ACC-030 隐私设置：非公开档案只展示信任摘要
    if (user.privacy or {}).get("profile_public") is False:
        return base
    return {
        **base,
        "bio": user.bio,
        "city": user.city,
        "skills": user.skills,
        "certifications": user.certifications,
        # ACC-013 服务定价与可接单时间（名片页承接下单）
        "service_rate_cents": user.service_rate_cents,
        "available_times": user.available_times,
        "accepting_orders": user.accepting_orders,
    }
