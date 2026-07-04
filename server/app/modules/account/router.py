from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.core.security import create_token, hash_password, verify_password

from .models import Block, LoginSession, User
from .service import credit_level

router = APIRouter(tags=["account"])


def _issue_token(db: Session, user: User, device: str) -> str:
    """ACC-005：每次登录建立会话，token 绑定会话可被吊销。"""
    session = LoginSession(user_id=user.id, device=device[:200])
    db.add(session)
    db.flush()
    return create_token(user.id, session.id)


# ---------- schemas ----------
class RegisterIn(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(default="", max_length=50)
    sms_code: str


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
    }


# ---------- auth (ACC-001/002) ----------
@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    if body.sms_code != settings.DEV_SMS_CODE:
        raise bad_request("验证码错误", "sms_code_invalid")
    if db.query(User).filter(User.phone == body.phone).first():
        raise conflict("手机号已注册", "phone_taken")
    user = User(
        phone=body.phone,
        password_hash=hash_password(body.password),
        nickname=body.nickname or f"用户{body.phone[-4:]}",
    )
    db.add(user)
    db.flush()
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user or user.is_deleted or not verify_password(body.password, user.password_hash):
        raise bad_request("手机号或密码错误", "bad_credentials")
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


@router.post("/auth/login-sms")
def login_sms(body: SmsLoginIn, db: Session = Depends(get_db), user_agent: str = Header(default="")):
    """验证码登录，未注册自动注册（ACC-001）。"""
    if body.sms_code != settings.DEV_SMS_CODE:
        raise bad_request("验证码错误", "sms_code_invalid")
    user = db.query(User).filter(User.phone == body.phone).first()
    if user and user.is_deleted:
        raise bad_request("账号已注销", "account_deleted")
    if not user:
        user = User(phone=body.phone, nickname=f"用户{body.phone[-4:]}")
        db.add(user)
        db.flush()
    return {"token": _issue_token(db, user, user_agent), "user": _me(user)}


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
    if user.is_verified:
        raise conflict("已完成实名认证", "already_verified")
    # 模拟 eKYC：生产环境调用第三方身份核验 + 人脸比对
    user.is_verified = True
    user.real_name = body.real_name
    db.add(user)
    return {"is_verified": True}


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
    }


# ---------- 公开名片与信用摘要（CRED-006）----------
@router.get("/users/{user_id}")
def public_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    return {
        "id": user.id,
        "nickname": user.nickname,
        "bio": user.bio,
        "city": user.city,
        "skills": user.skills,
        "is_verified": user.is_verified,
        "credit_score": user.credit_score,
        "rating_avg": user.rating_avg,
        "tasks_completed": user.tasks_completed,
    }
