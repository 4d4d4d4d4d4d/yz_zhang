from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.core.security import create_token, hash_password, verify_password

from .models import User

router = APIRouter(tags=["account"])


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
        "credit_score": user.credit_score,
        "rating_avg": user.rating_avg,
        "tasks_completed": user.tasks_completed,
    }


# ---------- auth (ACC-001/002) ----------
@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
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
    return {"token": create_token(user.id), "user": _me(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise bad_request("手机号或密码错误", "bad_credentials")
    return {"token": create_token(user.id), "user": _me(user)}


@router.post("/auth/login-sms")
def login_sms(body: SmsLoginIn, db: Session = Depends(get_db)):
    """验证码登录，未注册自动注册（ACC-001）。"""
    if body.sms_code != settings.DEV_SMS_CODE:
        raise bad_request("验证码错误", "sms_code_invalid")
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user:
        user = User(phone=body.phone, nickname=f"用户{body.phone[-4:]}")
        db.add(user)
        db.flush()
    return {"token": create_token(user.id), "user": _me(user)}


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
