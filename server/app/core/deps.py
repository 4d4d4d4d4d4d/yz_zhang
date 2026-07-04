from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import forbidden
from app.core.security import decode_token
from app.modules.account.models import User


def get_current_user(
    db: Session = Depends(get_db), authorization: str = Header(default="")
) -> User:
    if not authorization.startswith("Bearer "):
        raise forbidden("未登录", "unauthenticated")
    try:
        payload = decode_token(authorization.removeprefix("Bearer "))
    except Exception:
        raise forbidden("登录态无效", "unauthenticated")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise forbidden("用户不存在", "unauthenticated")
    # ACC-005 会话吊销检查（旧 token 无 sid 的跳过，兼容期）
    if payload.get("sid") is not None:
        from app.modules.account.models import LoginSession

        session = db.get(LoginSession, int(payload["sid"]))
        if not session or session.revoked:
            raise forbidden("登录态已失效，请重新登录", "session_revoked")
    if user.is_banned:
        raise forbidden("账号已被封禁，如有异议请申诉", "account_banned")
    if user.is_deleted:
        raise forbidden("账号已注销", "account_deleted")
    return user


def require_verified(user: User = Depends(get_current_user)) -> User:
    """ACC-020：接单/资金操作前强制实名。"""
    if not user.is_verified:
        raise forbidden("需先完成实名认证", "verification_required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise forbidden("需要管理员权限", "admin_required")
    return user
