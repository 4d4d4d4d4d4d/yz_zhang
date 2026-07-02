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
        user_id = decode_token(authorization.removeprefix("Bearer "))
    except Exception:
        raise forbidden("登录态无效", "unauthenticated")
    user = db.get(User, user_id)
    if not user:
        raise forbidden("用户不存在", "unauthenticated")
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
